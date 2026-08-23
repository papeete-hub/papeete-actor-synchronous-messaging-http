---
id: ADR-PASH-0001
title: "A binding is its own repo, not a module — HTTP first, addressed by name not lookup"
status: Accepted
date: 2026-08-22
supersedes: []
references:
  - ../src/papeete_actor_synchronous_messaging_http/mailbox.py
  - https://github.com/papeete-hub/papeete-actor-synchronous-messaging/blob/main/src/papeete_actor_synchronous_messaging/mailbox.py
---

# ADR-PASH-0001 — A binding is its own repo, not a module

## Context

`papeete-actor-synchronous-messaging` ships exactly one binding, `InProcessMailbox` — a direct
method call, one Python process. Its own `mailbox.py` already named what comes next: *"A queue,
an HTTP surface, a file drop or a GitHub issue is a NEW BINDING — every message already written
stays recognisable by its envelope."* Deploying a customer/waiter example to a real Kubernetes
cluster is what turned "later" into now: two pods cannot share a Python process, so something
has to carry `request`/`ack`/`query`/`answer` over a real network.

Two questions followed: where does this binding live, and how does one actor find another once
"the same process" stops being true.

## Decision

**A binding is its own repository, named `papeete-actor-synchronous-messaging-<medium>`, not a
module inside the core package.** `engine.py`'s `Engine` port already has this shape one level
down — Claude and OpenAI are adapters behind one method (`judge`) — but they ship as optional
extras *inside* the core package because an adapter there is small and stateless: one HTTP call
out, no server, no deploy shape of its own. A binding is heavier: `HttpMailbox` needs a running
server, and the deployable example that proves it needs its own `Dockerfile` and
`deploy/k8s/`. That's enough weight to earn a repo rather than a module, mirroring how
`papeete-product`/`papeete-deploy`/`papeete-platform` are already separate repos rather than
folders inside `papeete-actor`.

**`HttpMailbox` implements `Mailbox` — the port, not a subclass of `InProcessMailbox`.** The
core package's `mailbox.py` now declares a `Mailbox` `Protocol` (`register`, `deliver`) mirroring
`Engine`; this package fills it with real sockets and depends on nothing else from the core
package's `mailbox.py`.

**Addressing is a name, not a lookup — no service registry built here.** `deliver()` resolves
an addressee to `http://<name, lowercased>:8080/receive` by default. This reuses, rather than
reinvents, a mechanism that already exists: Docker Compose's embedded network DNS and a
Kubernetes `Service` both resolve a plain name to a reachable address for free, and
`papeete-deploy`'s own worked customer/waiter example already proves it (`app.py` there calls
`http://waiter:8080/` directly). Building an address book or a second registry here would
duplicate what the platform underneath already gives for free.

**No `GET /card`.** `SimpleActor.resolve()`'s own docstring, in the core package, is explicit:
*"a peer learns what another ships by READING its card, never by asking it... there is no door
for 'what are your doors'."* A live card-serving endpoint would be exactly that door. Instead,
`examples/customer` and `examples/waiter` each ship a static, identical copy of the small
`registry.yaml` + both cards, baked in at Docker build time — the same "discovery is static"
model the in-process example already uses, just carried into two separate images instead of one
checkout.

## Rationale

**Stdlib only.** `http.server` and `urllib.request` are what every other small HTTP actor in
this ecosystem already uses (`papeete-actor`'s `car-inspector`, `papeete-deploy`'s own
customer/waiter demo) — no framework to pin, upgrade, or explain to a reader for a binding this
small.

**A `Refusal` crosses the wire as a 400, not a crashed thread.** `simple-actor-protocol/v0`'s
refuse-never-repair rule is a *property of the protocol*, not of one binding — carrying a
refusal across HTTP as an ordinary error response, rather than letting it surface as an
unhandled exception in the request handler, is what keeps that property true regardless of
medium.

**`peers` narrows the convention, it never replaces it.** A socket-level test on `127.0.0.1`
has no hostnames to distinguish two actors by port alone, so `HttpMailbox(peers={name: url})`
overrides the default for names it lists. Every other name still resolves by convention — this
is an escape hatch for the cases the convention cannot cover, not a second addressing scheme.

## Consequences

- **This package depends on the core package only** (`papeete-actor-synchronous-messaging`),
  editable-local for now, same as the core package's own dependency on `papeete-actor`.
- ~~**The example duplicates a small registry + two cards across two Docker build contexts**,
  because each actor's folder must be a self-contained build context for
  `papeete-actor build`'s own convention (`docker build -t <tag> <folder>`, folder as context)
  to keep working unmodified. Accepted, gated by a test that the two copies stay identical
  (`tests/test_examples_agree.py`) rather than avoided by widening the build context.~~
  **Superseded by [ADR-PASH-0002](./ADR-PASH-0002-follow-the-core-packages-back-to-basics-reset.md):**
  the core package deleted the `Context`/`registry.yaml` coupling mechanism this consequence
  existed to support. There is no registry to bake in and no second copy to keep identical —
  `test_examples_agree.py` is deleted, not repurposed.
- **Open — a second binding.** GitHub issues was discussed and deliberately deferred: a
  genuinely different, higher-latency shape, worth its own repo once this one is proven, the
  same way OpenAI was added as a second engine only after Claude proved the engine port
  generalizes.
- **Open — cross-cluster / cross-namespace addressing.** The name-is-hostname convention holds
  inside one Compose project or one k8s namespace. Nothing here resolves a peer across a
  namespace or cluster boundary; that's `papeete-deploy`'s and `papeete-platform`'s territory if
  and when it's needed, not this binding's to solve.
