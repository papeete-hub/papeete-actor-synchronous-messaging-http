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
from papeete_actor_synchronous_messaging_http.mailbox import HttpMailbox

box = HttpMailbox()                          # binds 0.0.0.0:8080
actor = Actor.from_card(
    "path/to/actor-folder", mailbox=box,
    actions={"take-order": take_order}, queries={"order-status": order_status})
box.serve_forever()                          # blocks, answering one POST route per door
```

No `engines=` above — `take_order`/`order_status` are plain fact-checks against the actor's own
state, and neither door needs a vendor's judgement to answer
([ADR-PAS-0012](https://github.com/papeete-hub/papeete-actor-synchronous-messaging/blob/main/adr/ADR-PAS-0012-an-engine-is-for-judgement-a-fixed-rule-set-could-not-replace.md)).
`Actor` still accepts `engines={name: Engine(...)}` for a door whose own
`actor-synchronous-messaging.yaml` names one — this binding does not narrow that.

- **`register(actor)` / `deliver(*, from_, to, verb, door, payload)`** — the two methods
  `Mailbox` requires. `register()` reads the actor's own card and builds one `POST /<door-id>`
  route per door it declares — `actions` answer `request`, `queries` answer `query`
  ([ADR-PASH-0004](./adr/ADR-PASH-0004-one-http-route-per-door-not-one-generic-receive.md)).
  `deliver()` is the outbound half: `POST http://<addressee, lowercased>:8080/<door>`, JSON body
  `{"from": ..., "payload": {...}}`, reply parsed back with a plain `json.loads()` — no envelope,
  and no `verb`/`door` field either: the URL already says both, so the wire only ever carries the
  caller's identity and the business payload.
- **`serve_forever()`** — the inbound half. Each door's own route derives its `verb` from which
  of the actor's doors it is; the body's `payload`/`from` become the rest of `actor.receive()`'s
  arguments, and the reply — whatever plain dict the answering actor's own `work` produced —
  goes back as JSON, as-is. A `Refusal` at the membrane (undeclared door, wrong verb for it,
  `work` itself failing) comes back as an HTTP 400 rather than a crashed request thread — refuse,
  never repair, carried across the wire.
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

## Releasing

Tag-triggered, via [PyPI Trusted Publishing](https://docs.pypi.org/trusted-publishers/) (OIDC).
**No API token is stored anywhere** — GitHub mints a short-lived OIDC token per run and PyPI
trades it for an upload token. There is nothing to rotate and nothing to leak.

```bash
git tag v0.1.0 && git push origin v0.1.0     # .github/workflows/release.yml does the rest
```

### One-time setup

**1. A pending publisher on PyPI** — the project does not exist yet, so it is registered from
the publisher side rather than by a first manual upload. At
<https://pypi.org/manage/account/publishing/>, as a **GitHub** pending publisher:

| Field | Value |
|---|---|
| PyPI Project Name | `papeete-actor-synchronous-messaging-http` |
| Owner | `papeete-hub` |
| Repository name | `papeete-actor-synchronous-messaging-http` |
| Workflow name | `release.yml` |
| Environment name | `pypi` |

All five must match exactly — PyPI checks the OIDC claims against them and rejects the upload
otherwise. `release.yml` already declares `permissions: id-token: write` and
`environment: pypi`, which is what makes those claims present.

**2. The `pypi` GitHub environment** ✅ *created*. No secrets in it — it exists so the OIDC claim
carries an environment name for PyPI to match. Protection rules are **not** set and are worth
considering, because a release is irreversible: PyPI never allows re-uploading a version, even
after a delete. Required reviewers, and restricting deployments to tags matching `v*`, are the
two that earn their keep.

After the first successful release PyPI converts the pending publisher into a normal one
automatically; there is no second setup step.

**Blocked on a sibling, for now.** This package's own `pyproject.toml` pins
`papeete-actor-synchronous-messaging>=0.1.0`, which is not yet installable from PyPI under that
name — its own release lane's last run failed
(see that repo's own Actions history). `release.yml`'s build step resolves dependencies from
PyPI, not from this workspace's editable-local sibling checkout, so tagging and pushing here
will fail at `uv build`/install until that package publishes successfully first.

### What a release asserts

The workflow builds, installs the wheel into a clean venv, and imports `HttpMailbox` from it
before publishing — so a build that can't actually be imported fails the release instead of
shipping a package nobody can use. It then re-installs the exact version just published, from
PyPI itself, polling for CDN propagation rather than trusting the upload step's own exit code.

## Licence

MIT.
