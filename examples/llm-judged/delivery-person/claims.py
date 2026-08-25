"""The claim book — this actor's store of record, and the only thing `report-issue` writes.

THIS IS THE REPO'S ONE JUDGED DOOR (ADR-PAS-0012). `report-issue` names `engine: scripted`
(`actor-synchronous-messaging.yaml`) because "is this account of a late/wrong/damaged delivery
credible, and what remedy does it warrant" has no fixed table that could answer it — unlike
`examples/deterministic/waiter`'s table roster or menu, there is nothing here to look up. `claim-status`
names none: a pure lookup against this actor's own state, the same shape as
`examples/deterministic/waiter/order_book.py`'s `order_status`.

TWO SHAPES, AND THE DIFFERENCE IS THE POINT — same as `order_book.py`'s own note: THE ENTRY
(rich, structured, keeps the account as the claimant gave it, quoted and attributed) and THE
LINE (one string, the shape a caller reads back).

Kept local here rather than imported from the core package's own examples: this container is
its own deploy unit, not a checkout of the core repo's fixtures (ADR-PASH-0001's own
"standalone over shared" posture).
"""
from __future__ import annotations

import itertools

import yaml


class ClaimBook:
    """One entry per upheld claim. Append-only, and mine alone to write."""

    def __init__(self, keeper: str = "Delivery Person"):
        self.keeper = keeper
        self.entries: dict[str, dict] = {}
        self._counter = itertools.count(1)

    # ── the business surface: one plain method per door this actor actually answers ────────

    def report_issue(self, actor, payload: dict, from_: str, judged: dict | None = None) -> dict:
        """CALLED FOR EVERY `report-issue` — its own door names `engine: scripted`
        (`actor-synchronous-messaging.yaml`, ADR-PAS-0010), so `Actor.receive()` has already
        asked it by the time this runs and `judged` is that verdict. Written only on a claim
        upheld — there is nothing to record about a claim this actor denied, and an entry for
        it would make a denial look like an upheld claim it never was.
        """
        if not judged.get("accepted"):
            return judged
        claim = f"claim-{next(self._counter):04d}"
        entry = {
            "claim": claim,
            "door": "report-issue",
            "opened_by": from_,
            "subject": str(payload.get("subject", "")),
            "reported": {                            # THEIRS. Quoted, attributed, unedited.
                "by": from_,
                "means": str(payload.get("means", "")),
            },
            "remedy": judged.get("remedy"),
            "recorded_by": self.keeper,              # MINE. The write.
        }
        self.entries[claim] = entry
        return {**judged, "claim_id": claim,
                "line": f"{claim}: upheld — remedy: {entry['remedy']}"}

    def claim_status(self, actor, payload: dict, from_: str, judged: dict | None = None) -> dict:
        """A lookup, never a judgement. `determinism_sits_at_existence`: "do I hold a claim
        under this id?" is answered from this actor's own state — `claim-status` names no
        `engine:` either, so `Actor.receive()` never touched one to get here; `judged` is
        always `None`.
        """
        about = payload.get("about")
        if about:
            entry = self.entries.get(about)
            if entry is None:
                return {"says": f"{self.keeper} holds no claim under '{about}'."}
            return {"says": f"{about}: on record — '{entry['subject']}'", "claim": entry}
        return {"says": f"{self.keeper} holds {len(self.entries)} claim(s).",
                "claims": list(self.entries)}

    def render(self) -> str:
        """The claim book as YAML. A rendering of the store, never a second copy of it."""
        return yaml.safe_dump(
            {"kept_by": self.keeper, "entries": list(self.entries.values())},
            sort_keys=False, allow_unicode=True, width=96, default_flow_style=False,
        )
