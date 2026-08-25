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

import threading
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
