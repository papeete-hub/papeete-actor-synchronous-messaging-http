# Decision log (`ADR-PASH-*`)

Decisions owned by **this repo**: the `HttpMailbox` binding itself, its addressing convention,
and the deployable example that proves it.

**What does not belong here.** Anything about the protocol, the card contract, or the engine
port — those are `papeete-actor-synchronous-messaging`'s (`ADR-PAS-*`). This repo consumes them
at a pin and never re-authors them.

## The log

| ID | Title | Status |
|----|-------|--------|
| [ADR-PASH-0001](./ADR-PASH-0001-a-binding-is-its-own-repo-not-a-module.md) | A binding is its own repo, not a module — HTTP first, addressed by name not lookup | Accepted (one consequence superseded by ADR-PASH-0002) |
| [ADR-PASH-0002](./ADR-PASH-0002-follow-the-core-packages-back-to-basics-reset.md) | Follow the core package's back-to-basics reset — no envelope, no baked-in coupling registry | Accepted |
