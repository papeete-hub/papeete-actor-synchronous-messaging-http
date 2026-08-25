"""The Delivery Person, deployed for real: a container, an HttpMailbox, and one operator route.

STDLIB ONLY beyond the engine SDKs — the same choice every small actor in this ecosystem
already makes.

THE ONE DOOR A REAL VENDOR ANSWERS (ADR-PAS-0012). `report-issue` names `engine: scripted` in
its own card — a symbolic slot (ADR-PAS-0010), not a vendor name — and `ENGINE` below picks
which real `Engine` fills that slot at container start:

    ENGINE=scripted (default)   keyless, deterministic — builds and runs with no secrets, the
                                same posture `examples/deterministic` holds.
    ENGINE=claude               what a pair actually develops against locally
                                (ANTHROPIC_API_KEY, or `ant auth login`) — mirrors
                                papeete-actor-synchronous-messaging's own "claude: local
                                development" lane.
    ENGINE=openai               what a live-vendor conformance run asserts the protocol with
                                (OPENAI_API_KEY) — mirrors that package's own "openai: CI"
                                lane. Nothing here runs this automatically; see the README for
                                how to invoke it by hand.

Switching vendors is an env var, never a rebuild — the Dockerfile installs both `anthropic` and
`openai` alongside this package's own wheels, and `resolve()` (the core package's own factory)
imports whichever one `ENGINE` actually names.

`GET /card` IS NOT A LIVE DISCOVERY DOOR. `ADR-PASH-0001` still holds — no runtime endpoint
recomputes another actor's doors on demand. `card.yaml` is `papeete-actor-synchronous-messaging
describe .`'s output, run exactly once at Docker build time (see `Dockerfile`); this route reads
that file's bytes once at startup and serves the same fixed dict back on every request, never
recomputing it.
"""
import os
from pathlib import Path

import yaml
from papeete_actor_synchronous_messaging.actor import Actor
from papeete_actor_synchronous_messaging.engine import ScriptedEngine, resolve

from papeete_actor_synchronous_messaging_http.mailbox import HttpMailbox
from claims import ClaimBook

HERE = Path(__file__).resolve().parent
CARD = yaml.safe_load((HERE / "card.yaml").read_text())

ENGINE_SLOT = "scripted"                    # the name report-issue's own card declares
ENGINE_NAME = os.environ.get("ENGINE", "scripted")

# A DETERMINISTIC FALLBACK, NOT A JUDGEMENT (ADR-PAS-0012) — the same rules
# `papeete-actor-synchronous-messaging`'s own scripted fixture uses for this scenario, so
# `ENGINE=scripted` (the default) answers a `report-issue` sensibly with no key and no network.
SCRIPTED_RULES = [
    ("verb: request", {"accepted": True,
                       "because": "the account is specific and consistent with the tracking "
                                  "record.",
                       "remedy": "partial refund"}),
    ("verb: query", {"says": "I hold this and answer from my own records."}),
]


def _engine():
    if ENGINE_NAME == "scripted":
        return ScriptedEngine(SCRIPTED_RULES)
    return resolve(ENGINE_NAME)


NOTICE_SUBJECT = "package delivered"
NOTICE_MEANS = "left with the building concierge, signed for at drop-off"

_cell: dict = {}                     # filled with the actor after it boots — see below


def _notify_delivery() -> dict:
    """Open a real request/query exchange with the Buyer, over the network, and return what
    happened — the OTHER direction from `examples/deterministic/customer`'s `GET /order`: both actors here
    are actors, neither is a client."""
    delivery_person = _cell["actor"]
    ack = delivery_person.request(to="Buyer", action="delivery-notice", subject=NOTICE_SUBJECT,
                                  means=NOTICE_MEANS)
    answer = delivery_person.query(to="Buyer", query="delivery-status",
                                   about=ack.get("notice_id"),
                                   asks="what did you record for that delivery?")
    return {
        "coupling": "Delivery Person -> Buyer over HTTP",
        "request": {"subject": NOTICE_SUBJECT, "means": NOTICE_MEANS},
        "ack": ack,
        "answer": answer,
    }


def _card_route() -> dict:
    return CARD


if __name__ == "__main__":
    claim_book = ClaimBook()
    mailbox = HttpMailbox(routes={"/notify-delivery": _notify_delivery, "/card": _card_route})
    actor = Actor.from_card(
        HERE, engines={ENGINE_SLOT: _engine()}, mailbox=mailbox,
        actions={"report-issue": claim_book.report_issue},
        queries={"claim-status": claim_book.claim_status})
    _cell["actor"] = actor
    print(f"Delivery Person listening on :8080 — card {HERE}", flush=True)
    print(f"ENGINE={ENGINE_NAME} answers report-issue", flush=True)
    print("GET /notify-delivery triggers a real request + query exchange with the Buyer",
         flush=True)
    print("GET /card serves the composed card, baked in at build time", flush=True)
    mailbox.serve_forever()
