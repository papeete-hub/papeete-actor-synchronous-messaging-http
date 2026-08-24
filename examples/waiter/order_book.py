"""The order book — this actor's store of record, and the only thing it writes.

NOTHING HERE IS PROTOCOL. This package does not know what an accepted `take-order` means, or
what `order-status` answers with — those choices live entirely in
`take_order`/`give_table`/`order_status` below, plain methods `Actor.from_card()` is given
directly, one per door (`actions={"take-order": order_book.take_order, "give-table":
order_book.give_table}`, `queries={"order-status": order_book.order_status}` — ADR-PAS-0011). A
concrete actor fills this seam with whatever its own work really is — a POS system, a kitchen
printer, a spreadsheet — and binds nobody by doing so. *Behaviour is proposed, never contracted.*

NEITHER DOOR NAMES AN `engine:` (ADR-PAS-0012). "Does this table exist, and is the dish on
tonight's menu?" and "does this table exist, and is it free?" are both plain checks against this
actor's own state — a fixed roster (`TABLES`), a fixed menu (`MENU`), and a running set of who
is currently seated (`self.seated`). Neither question needed a vendor to answer it; asking one
would have made "accepted" mean "whatever the model felt like," not "on the roster and on the
menu."

TWO SHAPES, AND THE DIFFERENCE IS THE POINT.

    THE ENTRY      rich, structured, private. The store of record. It keeps the order and
                   the grounds AS THE TABLE GAVE THEM — quoted, attributed, never restated as
                   this actor's own finding — beside the disposition this actor's own check
                   reached.
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

    TABLES = {1, 2, 3, 4, 5, 6, 7, 8}
    MENU = {
        "the wild mushroom risotto",
        "barley risotto",
        "grilled salmon",
        "a green salad",
    }

    def __init__(self, keeper: str = "Waiter"):
        self.keeper = keeper
        self.entries: dict[str, dict] = {}
        self.seated: set[int] = set()
        self._counter = itertools.count(1)

    # ── the business surface: one plain method per door this actor actually answers ────────

    def take_order(self, actor, payload: dict, from_: str, judged: dict | None = None) -> dict:
        """CALLED FOR EVERY `take-order`. A plain fact-check, never a judgement: does the table
        exist, and is the dish on tonight's menu? Written only on acceptance — there is nothing
        to record about a table this actor turned away, and an entry for it would make a
        refusal look like a cancelled order it never took.
        """
        table_number = payload.get("table_number")
        subject = str(payload.get("subject", ""))
        if table_number not in self.TABLES:
            return {"accepted": False,
                    "because": f"table {table_number!r} is not one of my tables"}
        if subject.strip() not in self.MENU:
            return {"accepted": False,
                    "because": f"{subject!r} is not on tonight's menu"}

        order = f"order-{next(self._counter):04d}"
        entry = {
            "order": order,
            "door": "take-order",
            "opened_by": from_,
            "table_number": table_number,
            "subject": subject,
            "reported": {                            # THEIRS. Quoted, attributed, unedited.
                "by": from_,
                "means": str(payload.get("means", "")),
            },
            "recorded_by": self.keeper,              # MINE. The check and the write.
        }
        self.entries[order] = entry
        return {"accepted": True, "order_id": order,
                "line": f"{order}: recorded — '{subject}', as ordered by {from_}"}

    def give_table(self, actor, payload: dict, from_: str, judged: dict | None = None) -> dict:
        """CALLED FOR EVERY `give-table`. Table exists, and isn't already seated — a capacity
        check, not a judgement. Seating is remembered here so a second request for the same
        table is correctly refused rather than double-booked.
        """
        table_number = payload.get("table_number")
        if table_number not in self.TABLES:
            return {"accepted": False, "table_number": table_number}
        if table_number in self.seated:
            return {"accepted": False, "table_number": table_number}
        self.seated.add(table_number)
        return {"accepted": True, "table_number": table_number}

    def order_status(self, actor, payload: dict, from_: str, judged: dict | None = None) -> dict:
        """A lookup, never a judgement. `determinism_sits_at_existence`: "do I hold an order
        under this id?" is answered from this actor's own state — `order-status` names no
        `engine:` either, so `Actor.receive()` never touched one to get here; `judged` is
        always `None`.
        """
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
