---
id: ADR-PASH-0003
title: "A static, build-time-baked GET /card is not the door ADR-PASH-0001 rejected"
status: Accepted
date: 2026-08-23
supersedes: []
references:
  - ../examples/waiter/app.py
  - ../examples/waiter/Dockerfile
  - ../examples/customer/app.py
  - ../examples/customer/Dockerfile
  - ./ADR-PASH-0001-a-binding-is-its-own-repo-not-a-module.md
---

# ADR-PASH-0003 — A static, build-time-baked `GET /card` is not the door ADR-PASH-0001 rejected

## Context

A human wants to read an actor's composed card — what
`papeete-actor-synchronous-messaging describe FOLDER` already prints, as a static, pull-based
rendering — from a browser, against a deployment actually running, rather than by checking out
the repo and reading four YAML files by hand.

`ADR-PASH-0001` already ruled on a route named `/card`: *"No `GET /card`... a peer learns what
another ships by READING its card, never by asking it live... a live card-serving endpoint would
be exactly that door."* That decision is about DISCOVERY — one actor resolving another's doors
at request time, dynamically, as a substitute for reading the peer's card ahead of time. It
still holds, unmodified. It does not by itself answer a narrower question: is there room for a
human-facing, operator convenience that happens to be reachable at a path that also says `/card`?

## Decision

**Yes, and the two are kept structurally distinct, not merely by intent.** `examples/waiter/` and
`examples/customer/` each gain a `GET /card` route, wired through `HttpMailbox`'s existing
`routes` extension point — the same mechanism `customer/app.py`'s own `GET /order` already uses,
never the protocol's `request`/`query` verbs. What makes it NOT the door ADR-PASH-0001 rejected:

- **Computed once, at build time, never at request time.** Each `Dockerfile` runs
  `papeete-actor-synchronous-messaging describe .` exactly once, baking the result into the
  image as `card.yaml`. `app.py` reads that file once at process startup and closes over the
  parsed dict; the route handler returns that same object on every call. There is no code path
  from an inbound HTTP request to `card.load()` — the membrane a caller crosses is unchanged.
- **No actor calls it.** `decide.py`'s own coupling to the Waiter is still hardcoded door ids
  (`take-order`, `order-status`), exactly as ADR-PASH-0002 already settled — this route is never
  consulted by `app.py`'s own `_trigger_order()`, or by any `work` seam. It exists for a person
  at a browser, the same audience `GET /health` and `GET /order` already serve.
- **A stale build is a stale route, on purpose.** Because the file is baked in, not recomputed,
  a card route can go out of date the moment the four source YAML files change without a
  rebuild — the same staleness a checked-out copy of a peer's card already carries under
  ADR-PASH-0001's own "ships a copy of it" model. That's the accepted cost of "static", not a
  bug introduced here.

## Rationale

`routes` was already the sanctioned extension point for exactly this class of thing —
*"the one extension point this binding offers, for a deployment's own operator-facing
endpoint"* (`mailbox.py`'s own docstring, predating this ADR). `/order` already proved the
pattern: an HTTP GET that triggers or exposes something for a human, answered outside the
`request`/`query` membrane entirely. `/card` is the same shape, not a new one.

## Consequences

- `HttpMailbox` itself is unchanged — still zero built-in knowledge of cards, still exactly the
  port ADR-PASH-0001 described. This decision lives entirely in `examples/`.
- A deployment that wants this convenience pays one build-time `RUN`, one file, and one route
  per actor — small, and opt-in (nothing in `mailbox.py` requires it).
- Naming the route `/card` invites confusion with the door ADR-PASH-0001 rejected. Read together,
  the two ADRs are the disambiguation; a future actor wiring this same pattern should keep
  reading it from a `card.yaml` baked at build time, not from `card.load()` called inside the
  request handler — that line is the one this ADR actually draws.
