"""The notice book — this actor's store of record, and the only thing `delivery-notice` writes.

NOTHING HERE IS PROTOCOL. `delivery_notice`/`delivery_status` are plain methods, given straight
to `Actor.from_card()` one per door (`actions={"delivery-notice": notices.delivery_notice}`,
`queries={"delivery-status": notices.delivery_status}` — ADR-PAS-0011). NEITHER NAMES AN
`engine:` — "is there a real subject to record?" is a plain check, not a judgement; this pair's
one judged door is `examples/llm-judged/delivery-person`'s `report-issue` instead (ADR-PAS-0012). This is
the Buyer's own answering side — proof that both actors here are actors, and neither is a
client, the same property `examples/deterministic/customer`/`examples/deterministic/waiter` already demonstrate.

Kept local here rather than imported from the core package's own examples: this container is
its own deploy unit, not a checkout of the core repo's fixtures (ADR-PASH-0001's own
"standalone over shared" posture).
"""
from __future__ import annotations

import itertools

import yaml


class Notices:
    """One entry per recorded notice. Append-only, and mine alone to write."""

    def __init__(self, keeper: str = "Buyer"):
        self.keeper = keeper
        self.entries: dict[str, dict] = {}
        self._counter = itertools.count(1)

    # ── the business surface: one plain method per door this actor actually answers ────────

    def delivery_notice(self, actor, payload: dict, from_: str,
                        judged: dict | None = None) -> dict:
        """CALLED FOR EVERY `delivery-notice`. A plain check, never a judgement: is there a
        real subject to record? Written only on acceptance."""
        subject = str(payload.get("subject", "")).strip()
        if not subject:
            return {"accepted": False, "because": "no subject was given to record"}

        notice = f"notice-{next(self._counter):04d}"
        entry = {
            "notice": notice,
            "door": "delivery-notice",
            "opened_by": from_,
            "subject": subject,
            "reported": {                            # THEIRS. Quoted, attributed, unedited.
                "by": from_,
                "means": str(payload.get("means", "")),
            },
            "recorded_by": self.keeper,              # MINE. The check and the write.
        }
        self.entries[notice] = entry
        return {"accepted": True, "notice_id": notice,
                "line": f"{notice}: recorded — '{subject}'"}

    def delivery_status(self, actor, payload: dict, from_: str,
                        judged: dict | None = None) -> dict:
        """A lookup, never a judgement — this actor's own records answer it directly; this
        door names no `engine:` either, so `judged` is always `None`."""
        about = payload.get("about")
        if about:
            entry = self.entries.get(about)
            if entry is None:
                return {"says": f"{self.keeper} holds no notice under '{about}'."}
            return {"says": f"{about}: on record — '{entry['subject']}'", "notice": entry}
        return {"says": f"{self.keeper} holds {len(self.entries)} notice(s).",
                "notices": list(self.entries)}

    def render(self) -> str:
        return yaml.safe_dump(
            {"kept_by": self.keeper, "entries": list(self.entries.values())},
            sort_keys=False, allow_unicode=True, width=96, default_flow_style=False,
        )
