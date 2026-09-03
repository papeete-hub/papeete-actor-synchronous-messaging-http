"""`HttpMailbox`, proven over real sockets — no Docker, no k8s, no card file.

WHAT THIS FILE IS FOR. `papeete-actor-synchronous-messaging`'s own suite already proves the
membrane holds over `InProcessMailbox`. This file proves the *binding* holds over TCP: the same
`request`/`query` in, whatever the answering actor's own `work` hands back out, minted,
serialized, sent, parsed and answered by a second, wholly separate process-shaped actor — two
`Actor`s, each on its own `HttpMailbox`, each `serve_forever()`-ing in a background thread on
`127.0.0.1`.

NO CARD FILE, ON PURPOSE. Card loading, card-shape validation and door discovery are already
exercised by the core package's own suite; re-testing them here would be the second
implementation this ecosystem keeps warning itself against. `Card` is built directly in Python
instead — the smallest input that lets a real conversation happen.
"""
from __future__ import annotations

import logging
import threading
import time
from pathlib import Path

import pytest

from papeete_actor_synchronous_messaging.actor import Actor
from papeete_actor_synchronous_messaging.card import Card, Offer
from papeete_actor_synchronous_messaging.engine import ScriptedEngine

from papeete_actor_synchronous_messaging_http.mailbox import HttpMailbox

from conftest import free_port as _free_port
from conftest import wait_until_listening as _wait_until_listening


_OPEN_SCHEMA = {"properties": {}, "required": []}          # any payload conforms — see below


def _card(name: str, action_id: str, query_id: str) -> Card:
    """A minimal, conformant card — one action door, one query door.

    `request_schema` is a required `Offer` field since ADR-PAS-0009 (`Actor.receive()` checks
    every inbound payload against it) — `_OPEN_SCHEMA` (no `additionalProperties: False`, no
    `required`) accepts whatever this file's own tests send, since payload-shape conformance is
    the core package's own suite's job, not this binding's. Both doors name `engine="scripted"`
    (ADR-PAS-0010) and register no handler — the judged reply alone is the answer — so this
    file's tests only need an `engines={"scripted": ScriptedEngine(...)}` registry, no handler
    functions. `ScriptedEngine` here is exactly the keyless test double ADR-PAS-0012 endorses
    for CI — this file is testing the wire mechanism, not authoring a worked example's business
    logic, so it is unaffected by that ADR narrowing which doors the worked examples themselves
    (`examples/deterministic/waiter`, `examples/deterministic/customer` — neither names an
    `engine:` any more; `examples/llm-judged/delivery-person`'s `report-issue` is the one door
    in either pair that legitimately does) may use one.
    """
    return Card(
        path=Path(f"/dev/null/{name}"), name=name, description="d",
        data=(), messages=(),
        actions={action_id: Offer(id=action_id, means="test door", completion="an ack",
                                  request_schema=_OPEN_SCHEMA, engine="scripted")},
        queries={query_id: Offer(id=query_id, means="test door", completion="an answer",
                                 request_schema=_OPEN_SCHEMA, engine="scripted")},
    )


ACCEPTS = [
    ("verb: request", {"accepted": True, "because": "it's a test."}),
    ("verb: query", {"says": "answering from the other side of a real socket."}),
]


@pytest.fixture
def two_actors():
    """Two `Actor`s, each on its own `HttpMailbox`, each serving on a real port.

    `peers` is what makes this a TEST rather than a deployment: both actors are on
    `127.0.0.1`, distinguished only by port, so the name-is-hostname convention `deliver()`
    uses by default has nothing to resolve against — the two boxes tell each other exactly
    where the other one is, the same way a hand-written `--peer` flag would.
    """
    caller_card = _card("Caller", "ask", "ask-status")
    answerer_card = _card("Answerer", "answer-me", "answer-status")
    caller_port, answerer_port = _free_port(), _free_port()

    caller_box = HttpMailbox(host="127.0.0.1", port=caller_port,
                             peers={"Answerer": f"http://127.0.0.1:{answerer_port}"})
    answerer_box = HttpMailbox(host="127.0.0.1", port=answerer_port,
                               peers={"Caller": f"http://127.0.0.1:{caller_port}"})

    caller = Actor(caller_card, engines={"scripted": ScriptedEngine(ACCEPTS)}, mailbox=caller_box)
    answerer = Actor(answerer_card, engines={"scripted": ScriptedEngine(ACCEPTS)},
                     mailbox=answerer_box)

    threads = [threading.Thread(target=box.serve_forever, daemon=True)
               for box in (caller_box, answerer_box)]
    for t in threads:
        t.start()
    _wait_until_listening(caller_port)
    _wait_until_listening(answerer_port)

    yield caller, answerer

    caller_box.shutdown()
    answerer_box.shutdown()


def test_a_request_and_a_query_cross_a_real_socket(two_actors):
    caller, answerer = two_actors

    ack = caller.request(to="Answerer", action="answer-me", subject="s", means="m")
    assert ack["accepted"] is True

    answer = caller.query(to="Answerer", query="answer-status", about="s", asks="well?")
    assert answer["says"] == "answering from the other side of a real socket."


def test_the_reply_survives_json_round_tripping(two_actors):
    """Not just that a reply arrives — that it arrives as the SAME dict, byte for byte."""
    caller, answerer = two_actors

    ack = caller.request(to="Answerer", action="answer-me",
                         subject="a subject with 'quotes' and — an em dash",
                         means="means with\na newline")
    assert ack["accepted"] is True
    assert ack["because"] == "it's a test."


def test_health_and_a_custom_route_answer_over_get():
    """`/health` always answers, unconditionally. `routes` is the one extension point."""
    import json
    import urllib.request

    port = _free_port()
    box = HttpMailbox(host="127.0.0.1", port=port, routes={"/greet": lambda: {"says": "hi"}})
    box.register(Actor(_card("Solo", "act", "ask"), engines={"scripted": ScriptedEngine([])}))
    thread = threading.Thread(target=box.serve_forever, daemon=True)
    thread.start()
    _wait_until_listening(port)
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=5) as resp:
            assert json.loads(resp.read()) == {"status": "ok"}
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/greet", timeout=5) as resp:
            assert json.loads(resp.read()) == {"says": "hi"}
    finally:
        box.shutdown()


def test_an_unreachable_peer_is_a_delivery_error(two_actors):
    """`deliver()` never swallows a socket failure into a false accept — it raises."""
    from papeete_actor_synchronous_messaging_http.mailbox import DeliveryError

    caller, _ = two_actors
    with pytest.raises(DeliveryError, match="no actor reachable at 'Nobody'"):
        caller.request(to="Nobody", action="answer-me", subject="s", means="m")


# ── ADR-PASH-0005: every inbound call leaves exactly one record, whatever became of it ────────
#
# These four are one test each of the four outcomes `do_POST` can name. What they are really
# guarding is the ABSENCE that preceded them: an undeclared door and an unparseable body used to
# return before the span/log/metric block was ever entered, so a caller hammering the wrong path
# produced nothing at all — no line to find, and no way to tell it apart from a call that never
# reached the process.

_STRICT_SCHEMA = {"properties": {"n": {"type": "integer"}}, "required": ["n"]}


def _solo(schema: dict = _OPEN_SCHEMA) -> tuple[HttpMailbox, int]:
    """One registered actor on a real port, with one action door (`act`) and one query door."""
    port = _free_port()
    box = HttpMailbox(host="127.0.0.1", port=port)
    card = Card(
        path=Path("/dev/null/Solo"), name="Solo", description="d", data=(), messages=(),
        actions={"act": Offer(id="act", means="test door", completion="an ack",
                              request_schema=schema, engine="scripted")},
        queries={"ask": Offer(id="ask", means="test door", completion="an answer",
                              request_schema=schema, engine="scripted")},
    )
    box.register(Actor(card, engines={"scripted": ScriptedEngine(ACCEPTS)}))
    threading.Thread(target=box.serve_forever, daemon=True).start()
    _wait_until_listening(port)
    return box, port


def _post(port: int, path: str, body: bytes) -> int:
    """The status code alone — these tests are about what got RECORDED, not what came back."""
    import urllib.error
    import urllib.request

    request = urllib.request.Request(f"http://127.0.0.1:{port}{path}", data=body, method="POST",
                                     headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            return response.status
    except urllib.error.HTTPError as e:
        return e.code


def _access_lines(caplog, prefix: str = "do_POST ") -> list[str]:
    """The access lines recorded so far, waiting briefly for the one this call must produce.

    The client is answered by `_reply()` and the line is logged AFTER it, in `do_POST`'s own
    `finally` — so a test that asserts the moment `urlopen` returns is racing the server thread
    that is still finishing the request. Polling for one line, rather than sleeping a fixed
    amount, keeps the suite fast and keeps "exactly one line" a real assertion: the wait ends at
    the first record, and any second one would still be there to fail on."""
    deadline = time.monotonic() + 2.0
    while time.monotonic() < deadline:
        lines = [r.getMessage() for r in caplog.records if r.getMessage().startswith(prefix)]
        if lines:
            return lines
        time.sleep(0.02)
    return []


@pytest.mark.parametrize(
    "path, body, status, outcome",
    [
        ("/act", b'{"from": "t", "payload": {}}', 200, "accepted"),
        ("/no-such-door", b'{"from": "t", "payload": {}}', 404, "no-route"),
        ("/act", b"not json at all", 400, "bad-request"),
    ],
)
def test_every_post_leaves_exactly_one_access_line(caplog, path, body, status, outcome):
    caplog.set_level(logging.INFO)
    box, port = _solo()
    try:
        assert _post(port, path, body) == status
        lines = _access_lines(caplog)
    finally:
        box.shutdown()

    assert lines == [
        f"do_POST door={path[1:]} verb={'request' if outcome != 'no-route' else '-'} "
        f"outcome={outcome}"
    ]


def test_a_payload_the_schema_rejects_is_recorded_as_refused(caplog):
    """The case that motivated ADR-PASH-0005 in a consumer: `Actor.receive()` refuses the payload
    before any handler of the answering actor's own runs, so nothing downstream ever had the
    chance to say which call this was."""
    caplog.set_level(logging.INFO)
    box, port = _solo(_STRICT_SCHEMA)
    try:
        assert _post(port, "/act", b'{"from": "t", "payload": {}}') == 400
        lines = _access_lines(caplog)
    finally:
        box.shutdown()

    assert lines == ["do_POST door=act verb=request outcome=refused"]


def test_a_get_to_an_unknown_path_says_so(caplog):
    """...and `/health` stays silent, since a readiness probe firing every few seconds is not
    news."""
    import urllib.error
    import urllib.request

    caplog.set_level(logging.INFO)
    box, port = _solo()
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=5) as response:
            assert response.status == 200
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{port}/nope", timeout=5)
        except urllib.error.HTTPError as e:
            assert e.code == 404
        lines = _access_lines(caplog, "do_GET ")
    finally:
        box.shutdown()

    assert lines == ["do_GET path=/nope outcome=no-route"]
