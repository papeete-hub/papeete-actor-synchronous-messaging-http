"""What an accepted substitution actually does here — and why this actor calls another one.

NOTHING BELOW IS PROTOCOL MACHINERY. It is one actor's own business logic, local and
revisable, binding nobody. *Behaviour is proposed, never contracted.* `confirm_substitution`/
`substitution_decision` are plain methods, given straight to `Actor.from_card()` one per door
(`actions={"confirm-substitution": decisions.confirm_substitution}`, `queries={
"substitution-decision": decisions.substitution_decision}` — ADR-PAS-0011); this package no
longer resolves a declared coupling for you either — `confirm_substitution` calls the Waiter
back by the name it arrived under (`from_`) and by door ids this file simply knows, the same
way any real business actor knows the API of a service it depends on.

ACCEPTING A SUBSTITUTE IS NOT A JUDGEMENT CALL HERE (ADR-PAS-0012, narrowing ADR-PAS-0010). "Is
the substitute the same kind of dish, and is it something I still believe the kitchen has?" is
answered from this actor's own fixed knowledge (`_category`, `AVAILABLE_SUBSTITUTES`) — not a
vendor's opinion. This door names no `engine:` at all.

ACCEPTING A SUBSTITUTION IS NOT THE END OF IT, EVEN SO. The Waiter proposed it because the
kitchen ran out of something; accepting it is worthless unless the order the Waiter is about to
cook from actually changes. Two things this actor does not have stand in the way:

    KNOWLEDGE     "what does my order currently say?" — only the Waiter's order book holds
                  the answer. It is quoted into this actor's own record, never copied into it.
    COMPUTATION   writing the new order is a write into the Waiter's own state, judged by the
                  Waiter's own triage. This actor ASKS. It never writes there, and it does not
                  decide the outcome — it receives a reply, which may say no.

Kept local here rather than imported from the core package's own examples: this container is
its own deploy unit, not a checkout of the core repo's fixtures (ADR-PASH-0001's own
"standalone over shared" posture).
"""
from __future__ import annotations

import itertools

import yaml

# WHAT THIS ACTOR BELIEVES THE KITCHEN CAN STILL OFFER — its own knowledge, not the Waiter's,
# and not asked of anybody. A real actor would refresh this from wherever it actually hears
# about kitchen availability; this worked example owns a fixed set instead.
AVAILABLE_SUBSTITUTES = {"barley risotto"}


def _category(dish: str) -> str:
    """A DELIBERATELY NAIVE stand-in for "what kind of dish is this" — the last word of its
    name (".../barley risotto" and ".../wild mushroom risotto" both end in "risotto"). Good
    enough to decide "same category" without a vendor, which is the entire point."""
    words = dish.strip().lower().split()
    return words[-1] if words else ""


class Decisions:
    """One entry per substitution this actor has decided on. Append-only, and mine alone."""

    def __init__(self, keeper: str = "Customer"):
        self.keeper = keeper
        self.entries: dict[str, dict] = {}
        self._counter = itertools.count(1)

    # ── the business surface: one plain method per door this actor actually answers ────────

    def confirm_substitution(self, actor, payload: dict, from_: str,
                             judged: dict | None = None) -> dict:
        """CALLED FOR EVERY `confirm-substitution`. A plain check, never a judgement: same
        category as what it replaces, and still on this actor's own list of what the kitchen
        can offer.

        Everything the Waiter said arrives quoted, never restated as this actor's own
        finding — a caller reading `substitution-decision` later can go and check it at the
        source rather than trust it here.
        """
        table_number = payload.get("table_number")
        original_dish = str(payload.get("original_dish", ""))
        substitute = str(payload.get("subject", ""))

        if _category(original_dish) != _category(substitute) or not _category(substitute):
            return {"accepted": False,
                    "because": f"'{substitute}' is not the same kind of dish as "
                               f"'{original_dish}'"}
        if substitute not in AVAILABLE_SUBSTITUTES:
            return {"accepted": False,
                    "because": f"I have no reason to believe '{substitute}' is still available"}

        # 1. KNOWLEDGE THIS ACTOR DOES NOT HOLD.
        known = actor.query(
            to=from_, query="order-status",
            asks=f"what does my order currently say, before I confirm the swap to "
                 f"'{substitute}'?",
        )

        # 2. WORK THIS ACTOR MAY NOT DO. The Waiter's order book is the Waiter's to write, and
        #    its own checks are its own — a refusal here is a correct outcome, not a failure
        #    (the kitchen may have run out of the substitute too, by the time this reaches it).
        ack = actor.request(
            to=from_, action="take-order", table_number=table_number, subject=substitute,
            means=f"the substitute {from_} proposed, accepted at my table. Yours to judge, "
                  f"and yours to write if the kitchen still has it.",
        )

        decision = f"decision-{next(self._counter):04d}"
        self.entries[decision] = {
            "decision": decision,
            "subject": substitute,
            "proposed_by": from_,
            "waiter_said": known,                  # THEIRS. Quoted, never restated as mine.
            "waiter_ack": ack,
        }
        return {"accepted": True, "decision_id": decision,
                "line": f"{decision}: accepted '{substitute}' — {from_} said {ack!r}"}

    def substitution_decision(self, actor, payload: dict, from_: str,
                              judged: dict | None = None) -> dict:
        """A lookup, never a judgement — this actor's own records answer it directly, and this
        door names no `engine:` either; `judged` is always `None`."""
        about = payload.get("about")
        if about:
            entry = self.entries.get(about)
            if entry is None:
                return {"says": f"{self.keeper} holds no decision under '{about}'."}
            return {"says": f"{about}: on record — '{entry['subject']}'", "decision": entry}
        return {"says": f"{self.keeper} holds {len(self.entries)} decision(s).",
                "decisions": list(self.entries)}

    def render(self) -> str:
        return yaml.safe_dump(
            {"kept_by": self.keeper, "entries": list(self.entries.values())},
            sort_keys=False, allow_unicode=True, width=96, default_flow_style=False,
        )
