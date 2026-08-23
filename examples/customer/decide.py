"""What an accepted substitution actually does here — and why this actor calls another one.

NOTHING BELOW IS PROTOCOL MACHINERY. It is one actor's own business logic, local and
revisable, binding nobody. *Behaviour is proposed, never contracted.* This package no longer
resolves a declared coupling for you — `Decisions.work()` calls the Waiter back by the name it
arrived under (`from_`) and by door ids this file simply knows, the same way any real business
actor knows the API of a service it depends on.

ACCEPTING A SUBSTITUTION IS NOT THE END OF IT. The Waiter proposed it because the kitchen ran
out of something; accepting it is worthless unless the order the Waiter is about to cook from
actually changes. Two things this actor does not have stand in the way:

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


class Decisions:
    """One entry per substitution this actor has decided on. Append-only, and mine alone."""

    def __init__(self, keeper: str = "Customer"):
        self.keeper = keeper
        self.entries: dict[str, dict] = {}
        self._counter = itertools.count(1)

    def work(self, actor, offer, verb: str, payload: dict, from_: str) -> dict:
        if offer.id == "confirm-substitution":
            return self._confirm_substitution(actor, offer, verb, payload, from_)
        if offer.id == "substitution-decision":
            # A LOOKUP, NEVER A JUDGEMENT — this actor's own records answer it directly.
            return self._substitution_decision(payload)
        return actor.judge(offer, verb, payload, from_)

    def _confirm_substitution(self, actor, offer, verb: str, payload: dict,
                              from_: str) -> dict:
        """Run for every `confirm-substitution`.

        Everything the Waiter said arrives quoted, never restated as this actor's own
        finding — a caller reading `substitution-decision` later can go and check it at the
        source rather than trust it here.
        """
        judged = actor.judge(offer, verb, payload, from_)
        if not judged.get("accepted"):
            return judged

        subject = str(payload.get("subject", ""))

        # 1. KNOWLEDGE THIS ACTOR DOES NOT HOLD.
        known = actor.query(
            to=from_, query="order-status",
            asks=f"what does my order currently say, before I confirm the swap to '{subject}'?",
        )

        # 2. WORK THIS ACTOR MAY NOT DO. The Waiter's order book is the Waiter's to write, and
        #    its triage is its own — a refusal here is a correct outcome, not a failure (the
        #    kitchen may have run out of the substitute too, by the time this reaches it).
        ack = actor.request(
            to=from_, action="take-order", subject=subject,
            means=f"the substitute {from_} proposed, accepted at my table. Yours to judge, "
                  f"and yours to write if the kitchen still has it.",
        )

        decision = f"decision-{next(self._counter):04d}"
        self.entries[decision] = {
            "decision": decision,
            "subject": subject,
            "proposed_by": from_,
            "waiter_said": known,                  # THEIRS. Quoted, never restated as mine.
            "waiter_ack": ack,
        }
        return {**judged, "decision": decision,
                "line": f"{decision}: accepted '{subject}' — {from_} said {ack!r}"}

    def _substitution_decision(self, payload: dict) -> dict:
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
