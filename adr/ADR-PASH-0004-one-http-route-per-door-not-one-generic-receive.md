---
id: ADR-PASH-0004
title: "One HTTP route per door, not one generic /receive — the wire speaks business, not dispatch"
status: Accepted
date: 2026-08-24
supersedes: []
references:
  - ../src/papeete_actor_synchronous_messaging_http/mailbox.py
  - ./ADR-PASH-0001-a-binding-is-its-own-repo-not-a-module.md
  - ./ADR-PASH-0002-follow-the-core-packages-back-to-basics-reset.md
---

# ADR-PASH-0004 — One HTTP route per door, not one generic `/receive`

## Context

`ADR-PASH-0002` pinned the wire shape as one route, `POST /receive`, carrying
`{"from": ..., "verb": ..., "door": ..., "payload": {...}}` — a JSON-RPC-style envelope where
`verb`/`door` select, in the body, which of the answering actor's doors is meant. That shape
mirrors `Actor.receive(verb=, door=, payload=, from_=)` exactly, which was the point at the
time: no envelope object to build or parse, a straight pass-through of the core package's own
port.

The gap it leaves: `verb`/`door` are this ecosystem's *dispatch* vocabulary — how an `Actor`
sorts an inbound call to the right handler — not business vocabulary. A caller placing an order
has to know the word "door" and the literal string `"take-order"` sitting inside a `door:` field
to do it; nothing about *how the Waiter internally recognizes and routes that call* is any of
the caller's business, and yet the wire shape makes the caller spell it out. Hexagonal terms:
the adapter (`HttpMailbox`) is supposed to translate between an external vocabulary and the
port's generic call — `POST /receive` + a `door` field instead *forwards* the port's own generic
vocabulary onto the wire unchanged, rather than translating it into something the outside world
should actually see (an operation named `take-order`, full stop).

This is not a knock on where validation lives — `Actor.receive()`'s `request_schema` check
(`ADR-PAS-0009`) stays exactly where it is, in the core package, run once regardless of which
binding calls it. That is a *different* question (settled) from what a caller sees on the wire
(the actual subject of this ADR).

## Decision

**Every door gets its own route, named after the door's own `id` — `POST /<door-id>` — built
dynamically from the registered actor's own card, never hand-declared.** `register(actor)` now
also indexes `actor.card.actions` (each entry answered as `verb="request"`) and
`actor.card.queries` (`verb="query"`) into one `{path: verb}` table, keyed by `/<id>`. `do_POST`
looks the incoming path up in that table instead of comparing against a single constant; a path
outside it is a plain 404, same as today for anything outside `/receive`. `deliver()` addresses
`http://<peer>:8080/<door>` instead of always `.../receive`.

**The wire body drops `verb` and `door` entirely — the URL already says both.** A request body
is now just `{"from": ..., "payload": {...}}`. Nothing forwards the dispatch vocabulary anymore;
the only thing that crosses the wire is the caller's identity and the business payload.

**A door `id` reused across `actions` and `queries` on the same card is refused at
`register()`, not resolved by guessing.** A flat `/<id>` namespace cannot tell two doors with
the same id apart the way an explicit `verb` field once could. Nothing in
`synchronous-messaging-doors/v1` forbids the same `id` appearing once as an action and once as a
query, so this binding adds its own guard: `register()` raises `DeliveryError` if it finds one,
rather than silently routing every call to whichever dict happened to be indexed second. In
practice this is not a real modeling constraint — a door that means "try to do this" and one
that means "tell me about that" sharing one name was already a naming collision worth avoiding,
this just makes it loud instead of silent.

**`GET /health` and a deployment's own `routes` (an unrelated, GET-only extension point) are
untouched.** They live on `do_GET`'s own dispatch table, which this decision does not touch —
`do_POST`'s table is the only thing gaining door-awareness.

## Rationale

**The adapter's job is translation, not pass-through.** A GitHub-issues binding, whenever it
exists, will have its own idea of "this is a take-order" — a label, a title convention — with
nothing resembling `verb`/`door` fields at all; it will still end up calling the exact same
`actor.receive(verb="request", door="take-order", payload=..., from_=...)` `HttpMailbox` now
calls from a URL match. Both adapters converge on the identical port call *because* each one
translates its own external vocabulary into it, rather than one of them just relaying the port's
own generic shape verbatim. `POST /receive` was that second thing — technically working, but the
wrong side of the boundary was doing the talking.

**Nothing about validation, the core package, or `Card`/`Offer` changes.** `schema.py`,
`card.py`'s `_build_request_schema`, and `Actor.receive()` are entirely unaware this binding
exists, let alone how it names its routes — exactly the separation `ADR-PASH-0001` already
established (`HttpMailbox` fills the `Mailbox` port, it doesn't reach into the core package's
internals). This ADR only changes what `HttpMailbox` itself does with the bytes before and after
that call.

**Still no live discovery.** A caller must still know a peer's door ids ahead of time, exactly as
`ADR-PASH-0001`'s "no `GET /card`" already requires — `examples/customer/decide.py` already
hardcodes `take-order`/`order-status` as literals. Moving where that same, already-known string
sits (a URL segment instead of a JSON field) adds no new coupling; it removes a field that named
nothing the caller didn't already have to know.

## Consequences

- **Breaking wire change** — this package's own version bumps accordingly (`0.1.0` → `0.2.0`).
  Nothing upstream (the core package, `papeete-actor-message`) is affected; both sides of every
  call in this repo (`deliver()` and `do_POST`) are the same class, so the two examples and the
  test suite move in lockstep with no external coordination needed.
- `ADR-PASH-0002`'s wire-shape bullet (`POST /receive`, `verb`/`door` in the body) is
  **superseded by this ADR** — struck through there, not deleted, per this log's own convention
  for a partial supersession. Everything else `ADR-PASH-0002` decided (no envelope object,
  `Card`/`Offer` field set, dropping the coupling registry) is unaffected.
- **A door named `health`, or matching an existing custom `routes` key, is not guarded against.**
  `do_GET` and `do_POST` are separate dispatch tables on separate HTTP methods, so a door and a
  GET route sharing a path string do not actually collide at the protocol level; this is left
  unguarded as a non-problem rather than defended against speculatively.
- **Open — a second binding.** The GitHub-issues binding `ADR-PASH-0001` already deferred is the
  natural proof that this generalizes: its own "one label/title convention per door" surface,
  translating into the identical `actor.receive()` call, with nothing resembling `verb`/`door`
  fields anywhere in its own vocabulary.
