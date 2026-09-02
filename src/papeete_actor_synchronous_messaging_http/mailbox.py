"""`HttpMailbox` — the `Mailbox` port, filled with real sockets.

ONE ROUTE PER DOOR, NOT ONE ROUTE FOR THE PROTOCOL (ADR-PASH-0004). `register(actor)` reads the
registered actor's own card and builds one `POST` route per door it declares — `/take-order`,
`/order-status`, whatever that actor's own `actor-synchronous-messaging.yaml` names — rather than
funnelling every call through one generic `/receive` with `verb`/`door` fields in the body.
`verb`/`door` are `Actor.receive()`'s own DISPATCH vocabulary, not business vocabulary; a caller
placing an order should see `take-order`, not a JSON field naming it. The wire body is therefore
just `{"from": ..., "payload": {...}}` — the URL already says which door and, since a door only
ever lives in `actions` (→ `request`) or `queries` (→ `query`), which verb. Translating a URL
match back into `actor.receive(verb=, door=, payload=, from_=)` is this module's own job; nothing
about that call, `Card`/`Offer`, or `request_schema` validation changes — this ADR only changes
what crosses the socket, never who checks it on the other side. `GET /health` (always
`{"status": "ok"}`) is the one transport-level concern every deployed actor needs regardless of
protocol — a k8s `readinessProbe`/`livenessProbe` target, not a door. `routes` (see `__init__`) is
the one extension point for a deployment's own operator-facing endpoints, and lives on a separate,
GET-only dispatch table this decision does not touch.

ADDRESSING IS A NAME, NOT A LOOKUP. `deliver()` resolves an addressee to
`http://<name, lowercased>:8080/<door>` by default — no service registry, no address book. A
Kubernetes `Service` (or Docker Compose's own embedded DNS) already resolves a name to a
reachable address for free; this binding leans on that rather than building a second one.
`peers` exists only to override that convention for a test or a non-cluster deployment — see
its own docstring.

EVERY INBOUND CALL IS OBSERVABLE, INCLUDING THE ONES NO DOOR ANSWERS (ADR-PASH-0005). `do_POST`
opens its `SERVER` span, parented on whatever `traceparent` the caller sent, BEFORE it routes the
path or reads the body — and logs and meters exactly one line per call, from inside that span. So
an undeclared door and a malformed body are outcomes of their own (`no-route`, `bad-request`)
rather than early returns that produced no span, no metric and no log record at all; and every
record any code emits while answering a call — this module's own access line included — sits
inside a span whose trace id is the caller's, which is what lets a consumer's own logging stamp a
correlation id onto records this binding refused before any handler could bind one.

DISCOVERY OF DOORS STAYS STATIC, deliberately, exactly as the core package's own `Actor` and
`Card` document it: a peer learns what another ships by reading its card, never by asking it —
there is no door for "what are your doors". So there is no `GET /card` here, on purpose — adding
one would be exactly the anti-pattern that design rejects. A deployment that needs a peer's card
ships a copy of it (see this package's own `examples/`). Naming a door in its own URL doesn't
reopen that: a caller must still know the id ahead of time, the same way `examples/deterministic/
customer/decide.py` already hardcodes `take-order`/`order-status` as literals — only where that already-
known string sits (a URL segment, not a JSON field) has changed.
"""
from __future__ import annotations

import json
import logging
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Callable

from papeete_actor_synchronous_messaging.actor import Refusal

from . import _tracing

PORT = 8080
HEALTH_PATH = "/health"
# What stands in for the verb when no door matched the path — there IS no verb in that case, and
# a metric attribute this binding invented is more honest as a visible placeholder than as an
# empty string a query would silently treat as "missing label".
NO_VERB = "-"


class DeliveryError(RuntimeError):
    """The call names an addressee this binding could not reach, or reach cleanly."""


class HttpMailbox:
    """A `Mailbox`: `register()` names the one local actor; `deliver()`/`serve_forever()` are
    the outbound and inbound halves of the same port."""

    def __init__(self, *, host: str = "0.0.0.0", port: int = PORT,
                 peers: dict[str, str] | None = None,
                 routes: dict[str, Callable[[], dict]] | None = None):
        """`peers` MAPS AN ADDRESSEE'S NAME TO A BASE URL, overriding the name-is-hostname
        convention for names it lists. It exists for exactly two cases the convention cannot
        cover on its own: a socket-level test running two actors on `127.0.0.1` at different
        ports (nothing to distinguish by hostname), and a deployment whose network genuinely
        does not resolve a peer's name to its address. Every other name still resolves by
        convention — `peers` narrows, it never replaces the default.

        `routes` MAPS A GET PATH TO A NO-ARGUMENT CALLABLE returning a JSON-able dict — the
        one extension point this binding offers, for a deployment's own operator-facing
        endpoint (an actor triggering its own demo conversation, say). It is never how one
        actor answers another: that is always one of the `POST` routes `register()` builds
        from the actor's own doors (ADR-PASH-0004). `GET /health` always answers
        `{"status": "ok"}` and cannot be overridden.
        """
        self.host, self.port, self._peers = host, port, dict(peers or {})
        self._routes = dict(routes or {})
        self._doors: dict[str, str] = {}          # "/door-id" -> "request" | "query"
        self._actor = None
        self._server: ThreadingHTTPServer | None = None

    def register(self, actor) -> None:
        """Names the one local actor, and builds one `POST /<door-id>` route per door its own
        card declares (ADR-PASH-0004) — `actions` answer `request`, `queries` answer `query`.

        A door `id` declared as both an action and a query is refused here: a flat `/<id>`
        namespace has no `verb` field left to tell the two apart, unlike the old envelope.
        """
        if self._actor is not None:
            raise DeliveryError(
                f"this binding already answers for '{self._actor.name}' — one process, one "
                f"actor (a second `register()` is almost certainly a bug, not a second actor)"
            )
        collisions = sorted(set(actor.card.actions) & set(actor.card.queries))
        if collisions:
            raise DeliveryError(
                f"'{actor.name}' declares {collisions} as both an action and a query — a flat "
                f"HTTP route can't tell the two apart (ADR-PASH-0004); give one of them a "
                f"different id"
            )
        self._doors = {f"/{door_id}": "request" for door_id in actor.card.actions}
        self._doors.update({f"/{door_id}": "query" for door_id in actor.card.queries})
        self._actor = actor

    def _base_url(self, to: str) -> str:
        return self._peers.get(to) or f"http://{to.lower()}:{self.port}"

    def deliver(self, *, from_: str, to: str, verb: str, door: str, payload: dict) -> dict:
        """**Outbound.** POST the call to the addressee's own door, and return its reply.

        `verb` never crosses the wire — the door alone selects the route, and the answering
        process derives its own verb from which of its doors that is (ADR-PASH-0004); it stays
        a required parameter here only because `Mailbox`'s own port signature carries it, not
        because this binding's wire needs it. Never touches `self._actor` — a call this process
        SENDS is never addressed to itself, so outbound and inbound never share state beyond the
        socket. `to` does not need to travel on the wire either: the receiving process only ever
        answers for the one actor it registered.

        Wrapped in a CLIENT span, propagated via `_tracing.inject()` (W3C `traceparent`) so the
        answering process's own SERVER span (see `Handler.do_POST`) parents under it — and one
        `door_calls_total`/`door_latency_seconds` metric tick, `outcome` one of `accepted`
        (a reply came back), `refused` (the peer raised a `Refusal`, carried as an HTTP 400) or
        `error` (unreachable / not a clean HTTP exchange).
        """
        url = self._base_url(to) + "/" + door
        body = json.dumps({"from": from_, "payload": payload}).encode()
        start, outcome = time.monotonic(), "error"
        try:
            with _tracing.span(f"deliver {door}", _tracing.CLIENT,
                               {"door": door, "verb": verb, "to": to}):
                # `inject()` MUST run inside the span's own `with` block — it reads the
                # CURRENTLY ACTIVE span out of context to build `traceparent`; called before
                # `start_as_current_span` returns, there is no active span yet and the header
                # carries nothing (or a stale ambient one), silently breaking parent/child
                # propagation across the wire. Caught by the real end-to-end check (Tempo
                # showing two disconnected trace ids instead of one), not by any unit test —
                # `test_http_mailbox.py`/`test_deterministic_conversation.py` run with
                # `opentelemetry-api` absent, where this ordering is a no-op either way.
                headers = _tracing.inject({"Content-Type": "application/json"})
                request = urllib.request.Request(url, data=body, method="POST", headers=headers)
                try:
                    with urllib.request.urlopen(request, timeout=10) as response:
                        reply = json.loads(response.read())
                except urllib.error.HTTPError as e:
                    outcome = "refused"
                    raise DeliveryError(
                        f"'{to}' at {url} refused this call ({e.code}): {e.read().decode()}"
                    ) from e
                except (urllib.error.URLError, ConnectionError, TimeoutError) as e:
                    raise DeliveryError(f"no actor reachable at '{to}' ({url}): {e}") from e
                outcome = "accepted"
                return reply
        finally:
            logging.info("deliver door=%s verb=%s to=%s outcome=%s", door, verb, to, outcome)
            _tracing.record(door=door, verb=verb, outcome=outcome,
                            elapsed=time.monotonic() - start)

    def serve_forever(self) -> None:
        """**Inbound.** Block, answering each of the registered actor's own door routes with
        its reply."""
        if self._actor is None:
            raise DeliveryError("no local actor registered — call register() before serving")
        self._server = ThreadingHTTPServer((self.host, self.port), self._handler())
        try:
            self._server.serve_forever()
        finally:
            self._server = None

    def shutdown(self) -> None:
        if self._server is not None:
            self._server.shutdown()

    def _handler(self):
        actor = self._actor
        routes = self._routes
        doors = self._doors

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:                                # noqa: N802 — stdlib name
                if self.path == HEALTH_PATH:
                    return self._reply(200, {"status": "ok"})
                if self.path in routes:
                    return self._reply(200, routes[self.path]())
                # Deliberately the ONE inbound call this binding does not span or meter, but it
                # does say so: `/health` is a readiness probe firing every few seconds, and a
                # span per probe would bury every real call in a deployment's own traces. A GET
                # to anything else is a caller getting an address wrong, which is worth a line.
                logging.warning("do_GET path=%s outcome=no-route", self.path)
                self._reply(404, {"error": f"no route {self.path}"})

            def do_POST(self) -> None:                              # noqa: N802 — stdlib name
                """One span, one metric tick and one log line per call — ADR-PASH-0005.

                The span opens BEFORE the path is routed and BEFORE the body is read, which is
                the whole of the decision: an undeclared door and an unparseable body are
                things that happened TO this actor, and they used to return early, leaving a
                call that produced no span, no metric and no log record whatsoever —
                indistinguishable, from the outside, from a call that never arrived at all.

                `outcome` is one of `no-route` (nothing answers this path), `bad-request` (the
                body is not JSON), `refused` (the actor raised a `Refusal` — an undeclared
                door, a payload its `request_schema` rejects, a handler that failed),
                `accepted`, or `error` (anything `_dispatch` raised that is none of those).

                The log line and the metric sit INSIDE the span, not in a `finally` outside it,
                so they carry the caller's own trace context — a consumer stamping a
                correlation id onto its records from the active span (see
                `papeete-observability`) reaches even the calls refused before any handler of
                its own could run.
                """
                door = self.path[1:]
                verb = doors.get(self.path)
                with _tracing.span(door or self.path, _tracing.SERVER,
                                   {"door": door, "verb": verb or ""},
                                   context=_tracing.extract(self.headers)):
                    start, outcome = time.monotonic(), "error"
                    try:
                        outcome = self._dispatch(door, verb)
                    finally:
                        logging.info("do_POST door=%s verb=%s outcome=%s",
                                     door, verb or NO_VERB, outcome)
                        _tracing.record(door=door, verb=verb or NO_VERB, outcome=outcome,
                                        elapsed=time.monotonic() - start)

            def _dispatch(self, door: str, verb: str | None) -> str:
                """Answer the call, and name its outcome. Never logs and never meters — that is
                `do_POST`'s single place to do both, on every path out of here including the
                exceptional one."""
                if verb is None:
                    self._reply(404, {"error": f"no route {self.path}"})
                    return "no-route"

                length = int(self.headers.get("Content-Length", 0))
                try:
                    body = json.loads(self.rfile.read(length) or b"{}")
                except json.JSONDecodeError:
                    self._reply(400, {"error": "body is not valid JSON"})
                    return "bad-request"

                try:
                    reply = actor.receive(verb=verb, door=door,
                                          payload=body.get("payload") or {},
                                          from_=body.get("from"))
                except Refusal as e:
                    # REFUSE, NEVER REPAIR — carried across the wire rather than swallowed. The
                    # sender's own `deliver()` turns this back into a `DeliveryError`.
                    self._reply(400, {"error": str(e)})
                    return "refused"

                self._reply(200, reply)
                return "accepted"

            def _reply(self, status: int, body: dict) -> None:
                payload = json.dumps(body).encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

            def log_message(self, *args) -> None:                   # keep container logs quiet
                pass

        return Handler
