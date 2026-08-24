---
id: ADR-PASH-0002
title: "Follow the core package's back-to-basics reset — no envelope, no baked-in coupling registry"
status: Accepted
date: 2026-08-23
supersedes: []
references:
  - ../src/papeete_actor_synchronous_messaging_http/mailbox.py
  - ./ADR-PASH-0001-a-binding-is-its-own-repo-not-a-module.md
  - https://github.com/papeete-hub/papeete-actor-synchronous-messaging/blob/main/src/papeete_actor_synchronous_messaging/mailbox.py
  - https://github.com/papeete-hub/papeete-actor-synchronous-messaging/blob/main/src/papeete_actor_synchronous_messaging/card.py
---

# ADR-PASH-0002 — Follow the core package's back-to-basics reset

## Context

`ADR-PASH-0001` (accepted 2026-08-22) built this binding against a snapshot of
`papeete-actor-synchronous-messaging` that no longer exists. The very next day that core package
took a "back to basics" pass (`ADR-PAS-0007`) that removed the envelope/message contract
entirely (`Message`, `.to_mapping()`/`.from_mapping()`, `.envelope`, `.ref`, `verb: ack`/
`verb: answer`), on top of an earlier change that already removed `Context`/`registry.yaml`-based
coupling resolution. Nothing in this repo had been touched since, so it stopped importing —
every module here reached for names the dependency it pins no longer has.

This ADR is not a reversal of ADR-PASH-0001. Every architectural decision that ADR made — a
binding is its own repo, `HttpMailbox` fills the `Mailbox` port (not a subclass), addressing is
name-is-hostname with `peers` as an escape hatch, there is no `GET /card` — is still sound and
still holds, unmodified, in the current `mailbox.py`. What changed is only the concrete shape of
the port and the actor it wraps, and one consequence of ADR-PASH-0001 that depended on a coupling
mechanism the core package has since deleted outright.

## Decision

**Follow the core package's contract exactly, as it now stands, not as ADR-PASH-0001 described
it.** Concretely:

- ~~`deliver()` takes `(*, from_, to, verb, door, payload) -> dict` — a plain lookup-and-call, no
  envelope object. The wire body is `{"from": ..., "verb": ..., "door": ..., "payload": ...}`;
  `to` never travels, since the receiving process only ever answers for the one actor it
  registered.~~ **The wire shape is superseded by
  [ADR-PASH-0004](./ADR-PASH-0004-one-http-route-per-door-not-one-generic-receive.md):** `verb`/
  `door` no longer travel in the body — each door gets its own route instead. `deliver()`'s own
  Python signature (`from_, to, verb, door, payload`) is unchanged; only what it puts on the wire
  is. `to` still never travels, unchanged.
- `do_POST` calls `actor.receive(verb=..., door=..., payload=..., from_=...)` and writes the
  reply dict back as `json.dumps(reply)` — nothing to unwrap, nothing to re-wrap.
- `SimpleActor`/`SimpleCard` are gone; this repo's tests and examples now build a `Card` with
  the current field set (`path, name, description, data, messages, actions, queries`) and call
  `Actor.from_card(folder, engine, mailbox=..., work=...)` — no `context=` kwarg, the path is the
  actor's own folder, holding all four of its files directly.
- A reply carries no fixed shape. `verb: ack`/`verb: answer` are gone; what crosses back is
  whatever the answering actor's own `work` produced, in that actor's own vocabulary
  (`order_book.py`'s `accepted`/`order`/`line`, `decide.py`'s `accepted`/`decision`/`line`).

**Drop the baked-in coupling registry — `Context`/`registry.yaml` no longer exists upstream to
motivate it.** ADR-PASH-0001's consequence that each actor's Docker build context carries a
small `registry.yaml` plus a copy of both actors' cards, gated by
`tests/test_examples_agree.py`, existed *because* the core package once resolved a declared
`dependencies:` coupling from exactly that shape. The core package's own `card.py` now says
plainly: an actor that needs another one just calls it by the mailbox name it already has — door
ids on a peer are the calling actor's own business knowledge, nothing upstream resolves or gates
that. `examples/customer/decide.py` (both in the core repo and, copied, in this one) already
lives by that rule: it calls the Waiter's `take-order`/`order-status` doors as literals, the same
way `examples/customer/app.py`'s own `/order` trigger now does. This repo follows suit:
`context/` is deleted from both example folders, `test_examples_agree.py` is deleted with it (it
had nothing left to gate), and each actor's folder now carries only its own four files
(`actor.yaml`, `actor-data.yaml`, `actor-message.yaml`, `actor-synchronous-messaging.yaml`) plus
its own `work` module (`order_book.py` / `decide.py`).

**This package now also consumes `papeete-actor-message` at a pin, transitively.** The core
package's `card.py` depends on it directly (for the data dictionary and message-catalog gates
that back every door); `examples/build-wheels.sh` gained a fourth wheel build so
`docker build`'s local-wheel install keeps resolving offline.

## Rationale

Same rationale ADR-PASH-0001 already gave for standalone-copy-over-shared-import
(`order_book.py`/`decide.py` are copied into this repo rather than imported from the core
package's own `examples/`) — this container is its own deploy unit, not a checkout of the core
repo's fixtures. Deleting the coupling registry rather than inventing a replacement follows the
same discipline the core package applied to itself: don't re-author a contract another package
owns, including the contract for how (or whether) a coupling gets declared.

## Consequences

- ADR-PASH-0001's "no coupling registry built here... registry.yaml baked in" consequence is
  **superseded by this ADR** — see the strikethrough note left on that section. The rest of
  ADR-PASH-0001 (own-repo, port-not-subclass, name-is-hostname addressing, no `GET /card`) is
  unaffected and remains the current design.
- `tests/test_examples_agree.py` is deleted, not preserved as a no-op — there are no longer two
  copies of anything to compare.
- A peer's door ids are now genuinely just business knowledge a caller's own code carries
  (`app.py`, `decide.py`) — nothing in this repo or the core package validates that a caller
  addresses a door its peer actually declares. A typo in a door id fails at the peer's own
  membrane (`Refusal`, HTTP 400), not before the call is sent.
