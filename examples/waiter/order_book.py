"""The order book — this actor's store of record, and the only thing it writes.

NOTHING HERE IS PROTOCOL. This package does not know what an accepted `take-order` means, or
what `order-status` answers with — those choices live entirely in `work()` below, the callable
`Actor.from_card()` is given for this folder. A concrete actor fills this seam with
whatever its own work really is — a POS system, a kitchen printer, a spreadsheet — and binds
nobody by doing so. *Behaviour is proposed, never contracted.*

TWO SHAPES, AND THE DIFFERENCE IS THE POINT.

    THE ENTRY      rich, structured, private. The store of record. It keeps the order and
                   the grounds AS THE TABLE GAVE THEM — quoted, attributed, never restated as
                   this actor's own finding — beside the disposition its own engine reached.
    THE LINE       one string, the only shape quoted back over the wire when a caller asks.

This container holds the entries in memory, so a restart loses them — a worked example, not a
production kitchen. Kept local here rather than imported from the core package's own examples:
this container is its own deploy unit, not a checkout of the core repo's fixtures
(ADR-PASH-0001's own "standalone over shared" posture).
"""
from __future__ import annotations

import itertools

import yaml


class OrderBook:
    """One entry per accepted table. Append-only, and mine alone to write."""

    def __init__(self, keeper: str = "Waiter"):
        self.keeper = keeper
        self.entries: dict[str, dict] = {}
        self._counter = itertools.count(1)

    # ── the work seam: what Actor hands this actor's doors ─────────────────────────

    def work(self, actor, offer, verb: str, payload: dict, from_: str) -> dict:
        """The whole of this actor's business logic. Dispatch by door id, nothing more."""
        if offer.id == "take-order":
            return self._take_order(actor, offer, verb, payload, from_)
        if offer.id == "order-status":
            # A LOOKUP, NEVER A JUDGEMENT. `determinism_sits_at_existence`: "do I hold an
            # order under this id?" is answered from this actor's own state, and the engine
            # is not consulted to find out — this is exactly the call this package no longer
            # makes for you, so the example makes it itself.
            return self._order_status(payload)
        return actor.judge(offer, verb, payload, from_)     # give-table: judge, nothing to write

    def _take_order(self, actor, offer, verb: str, payload: dict, from_: str) -> dict:
        """CALLED ON EVERY take-order. Written only on acceptance — there is nothing to
        record about a table this actor turned away, and an entry for it would make a
        refusal look like a cancelled order it never took."""
        judged = actor.judge(offer, verb, payload, from_)
        if not judged.get("accepted"):
            return judged
        order = f"order-{next(self._counter):04d}"
        entry = {
            "order": order,
            "door": "take-order",
            "opened_by": from_,
            "subject": str(payload.get("subject", "")),
            "reported": {                            # THEIRS. Quoted, attributed, unedited.
                "by": from_,
                "means": str(payload.get("means", "")),
            },
            "recorded_by": self.keeper,              # MINE. The judgement and the write.
        }
        self.entries[order] = entry
        return {**judged, "order": order,
                "line": f"{order}: recorded — '{entry['subject']}', as ordered by {from_}"}

    def _order_status(self, payload: dict) -> dict:
        """A lookup, never a judgement — the engine is not consulted for what this already
        knows from its own state."""
        about = payload.get("about")
        if about:
            entry = self.entries.get(about)
            if entry is None:
                return {"says": f"{self.keeper} holds no order under '{about}'."}
            return {"says": f"{about}: on record — '{entry['subject']}'", "order": entry}
        return {"says": f"{self.keeper} holds {len(self.entries)} order(s).",
                "orders": list(self.entries)}

    def render(self) -> str:
        """The order book as YAML. A rendering of the store, never a second copy of it."""
        return yaml.safe_dump(
            {"kept_by": self.keeper, "entries": list(self.entries.values())},
            sort_keys=False, allow_unicode=True, width=96, default_flow_style=False,
        )
