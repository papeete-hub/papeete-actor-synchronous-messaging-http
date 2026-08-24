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
| [ADR-PASH-0003](./ADR-PASH-0003-a-static-baked-card-route-is-not-the-door-adr-pash-0001-rejected.md) | A static, build-time-baked GET /card is not the door ADR-PASH-0001 rejected | Accepted |
| [ADR-PASH-0004](./ADR-PASH-0004-one-http-route-per-door-not-one-generic-receive.md) | One HTTP route per door, not one generic /receive — the wire speaks business, not dispatch | Accepted (partially supersedes ADR-PASH-0002's wire shape) |
