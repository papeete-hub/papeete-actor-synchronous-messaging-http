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

DISCOVERY OF DOORS STAYS STATIC, deliberately, exactly as the core package's own `Actor` and
`Card` document it: a peer learns what another ships by reading its card, never by asking it —
there is no door for "what are your doors". So there is no `GET /card` here, on purpose — adding
one would be exactly the anti-pattern that design rejects. A deployment that needs a peer's card
ships a copy of it (see this package's own `examples/`). Naming a door in its own URL doesn't
reopen that: a caller must still know the id ahead of time, the same way `examples/customer/
decide.py` already hardcodes `take-order`/`order-status` as literals — only where that already-
known string sits (a URL segment, not a JSON field) has changed.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Callable

from papeete_actor_synchronous_messaging.actor import Refusal

PORT = 8080
HEALTH_PATH = "/health"


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
        """
        url = self._base_url(to) + "/" + door
        body = json.dumps({"from": from_, "payload": payload}).encode()
        request = urllib.request.Request(
            url, data=body, method="POST",
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(request, timeout=10) as response:
                return json.loads(response.read())
        except urllib.error.HTTPError as e:
            raise DeliveryError(
                f"'{to}' at {url} refused this call ({e.code}): {e.read().decode()}"
            ) from e
        except (urllib.error.URLError, ConnectionError, TimeoutError) as e:
            raise DeliveryError(f"no actor reachable at '{to}' ({url}): {e}") from e

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
                self._reply(404, {"error": f"no route {self.path}"})

            def do_POST(self) -> None:                              # noqa: N802 — stdlib name
                verb = doors.get(self.path)
                if verb is None:
                    return self._reply(404, {"error": f"no route {self.path}"})
                length = int(self.headers.get("Content-Length", 0))
                try:
                    body = json.loads(self.rfile.read(length) or b"{}")
                except json.JSONDecodeError:
                    return self._reply(400, {"error": "body is not valid JSON"})

                try:
                    reply = actor.receive(verb=verb, door=self.path[1:],
                                          payload=body.get("payload") or {},
                                          from_=body.get("from"))
                except Refusal as e:
                    # REFUSE, NEVER REPAIR — carried across the wire rather than swallowed.
                    # The sender's own `deliver()` turns this back into a `DeliveryError`.
                    return self._reply(400, {"error": str(e)})
                self._reply(200, reply)

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
