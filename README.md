# papeete-actor-synchronous-messaging-http

An HTTP binding for [`papeete-actor-synchronous-messaging`](https://github.com/papeete-hub/papeete-actor-synchronous-messaging)
— one class, `HttpMailbox`, filling the `Mailbox` port that package's own `mailbox.py` already
names: *"A queue, an HTTP surface, a file drop or a GitHub issue is a NEW BINDING, not a variant
of this one."*

```bash
pip install papeete-actor-synchronous-messaging-http
```

## Why a separate package

`papeete-actor-synchronous-messaging` ships `InProcessMailbox` — a direct method call, one
Python process, no network. That's enough to prove the *protocol*, and it is deliberately all
that package carries: no HTTP framework, no server, no deploy shape. A binding heavy enough to
need its own running server and its own deploy story (Dockerfile, k8s manifests) gets its own
package, the same way `engine.py`'s `Engine` port gets a separate adapter per vendor
(`engines/claude.py`, `engines/openai.py`) — except here the adapter is a whole repo, because a
binding is heavier than a single `judge()` call.

## `HttpMailbox`

```python
from papeete_actor_synchronous_messaging.actor import Actor
from papeete_actor_synchronous_messaging.engine import ScriptedEngine
from papeete_actor_synchronous_messaging_http.mailbox import HttpMailbox

box = HttpMailbox()                          # binds 0.0.0.0:8080
actor = Actor.from_card("path/to/actor-folder", ScriptedEngine([...]), mailbox=box)
box.serve_forever()                          # blocks, answering POST /receive
```

- **`register(actor)` / `deliver(*, from_, to, verb, door, payload)`** — the two methods
  `Mailbox` requires. `deliver()` is the outbound half: `POST http://<addressee,
  lowercased>:8080/receive`, JSON body `{"from": ..., "verb": ..., "door": ..., "payload": {...}}`,
  reply parsed back with a plain `json.loads()` — there is no envelope to build or unwrap.
- **`serve_forever()`** — the inbound half. One route, `POST /receive`; the body's `verb`/`door`/
  `payload`/`from` become the arguments to `actor.receive()`, and the reply — whatever plain dict
  the answering actor's own `work` produced — goes back as JSON, as-is. A `Refusal` at the
  membrane (undeclared door, wrong verb for it, `work` itself failing) comes back as an HTTP 400
  rather than a crashed request thread — refuse, never repair, carried across the wire.
- **Addressing is a name, not a lookup.** No service registry, no address book: the addressee's
  own name, lowercased, IS the hostname — a Kubernetes `Service` or Docker Compose's embedded
  DNS resolves that to a real address for free. `peers={name: base_url}` overrides the
  convention for names it lists, for the cases the convention can't cover on its own (a
  socket-level test on `127.0.0.1`, a network that genuinely doesn't resolve peer names).

**No `GET /card`.** Card discovery stays static — a peer learns what another ships by reading its
card, never by asking it live. A deployment that needs a peer's card ships a copy of it; door ids
on a peer are the calling actor's own business knowledge (see `examples/customer/decide.py`),
nothing here resolves or gates that.

## `examples/` — a real, deployable pair

`examples/customer/` and `examples/waiter/` are the same conversation
`papeete-actor-synchronous-messaging`'s own in-process scenario proves, wired to `HttpMailbox`
and shaped to build and deploy like any other actor in this ecosystem
(`actor.yaml` + `Dockerfile`, `deploy/k8s/base` + `overlays/develop`, per `papeete-actor`'s own
`ADR-PA-0025` convention). See `examples/README.md` for the exact build/deploy commands, local
and on Kubernetes.

## Test

```bash
uv run --extra dev pytest
```

No Docker, no k8s — two `Actor`s, each on its own `HttpMailbox`, each `serve_forever()`ing
in a background thread on `127.0.0.1`. Real sockets, real JSON, no mock.

## Licence

MIT.
