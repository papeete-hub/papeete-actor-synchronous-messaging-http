"""`HttpMailbox` — the `Mailbox` port, filled with real sockets.

ONE ROUTE FOR THE PROTOCOL. `POST /receive` is the whole messaging surface: a JSON body shaped
`{"from": ..., "verb": ..., "door": ..., "payload": {...}}` in, the local actor's reply out —
whatever plain dict its own `work` produced. There is no envelope to build or parse here;
`papeete-actor-synchronous-messaging`'s own `Mailbox` port is already just a lookup and a call
(`deliver(*, from_, to, verb, door, payload) -> Any`), and this module only ever moves that over
a socket. `GET /health` (always `{"status": "ok"}`) is the one transport-level concern every
deployed actor needs regardless of protocol — a k8s `readinessProbe`/`livenessProbe` target, not
a door. `routes` (see `__init__`) is the one extension point for a deployment's own
operator-facing endpoints.

ADDRESSING IS A NAME, NOT A LOOKUP. `deliver()` resolves an addressee to
`http://<name, lowercased>:8080/receive` by default — no service registry, no address book. A
Kubernetes `Service` (or Docker Compose's own embedded DNS) already resolves a name to a
reachable address for free; this binding leans on that rather than building a second one.
`peers` exists only to override that convention for a test or a non-cluster deployment — see
its own docstring.

DISCOVERY OF DOORS STAYS STATIC, deliberately, exactly as the core package's own `Actor` and
`Card` document it: a peer learns what another ships by reading its card, never by asking it —
there is no door for "what are your doors". So there is no `GET /card` here, on purpose — adding
one would be exactly the anti-pattern that design rejects. A deployment that needs a peer's card
ships a copy of it (see this package's own `examples/`).
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Callable

from papeete_actor_synchronous_messaging.actor import Refusal

PORT = 8080
PATH = "/receive"
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
        actor answers another: that is always `POST /receive`. `GET /health` always answers
        `{"status": "ok"}` and cannot be overridden.
        """
        self.host, self.port, self._peers = host, port, dict(peers or {})
        self._routes = dict(routes or {})
        self._actor = None
        self._server: ThreadingHTTPServer | None = None

    def register(self, actor) -> None:
        if self._actor is not None:
            raise DeliveryError(
                f"this binding already answers for '{self._actor.name}' — one process, one "
                f"actor (a second `register()` is almost certainly a bug, not a second actor)"
            )
        self._actor = actor

    def _base_url(self, to: str) -> str:
        return self._peers.get(to) or f"http://{to.lower()}:{self.port}"

    def deliver(self, *, from_: str, to: str, verb: str, door: str, payload: dict) -> dict:
        """**Outbound.** POST the call to the addressee, and return its reply.

        Never touches `self._actor` — a call this process SENDS is never addressed to itself,
        so outbound and inbound never share state beyond the socket. `to` does not need to
        travel on the wire: the receiving process only ever answers for the one actor it
        registered.
        """
        url = self._base_url(to) + PATH
        body = json.dumps({"from": from_, "verb": verb, "door": door,
                           "payload": payload}).encode()
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
        """**Inbound.** Block, answering `POST /receive` with the local actor's reply."""
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

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:                                # noqa: N802 — stdlib name
                if self.path == HEALTH_PATH:
                    return self._reply(200, {"status": "ok"})
                if self.path in routes:
                    return self._reply(200, routes[self.path]())
                self._reply(404, {"error": f"no route {self.path}"})

            def do_POST(self) -> None:                              # noqa: N802 — stdlib name
                if self.path != PATH:
                    return self._reply(404, {"error": f"no route {self.path}"})
                length = int(self.headers.get("Content-Length", 0))
                try:
                    body = json.loads(self.rfile.read(length) or b"{}")
                except json.JSONDecodeError:
                    return self._reply(400, {"error": "body is not valid JSON"})

                try:
                    reply = actor.receive(verb=body.get("verb"), door=body.get("door"),
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
