"""The Buyer, deployed for real: a container, an HttpMailbox, and one operator-facing route.

STDLIB ONLY, on purpose — the same choice every small actor in this ecosystem already makes.
Names no `engine:` anywhere on its own card, so it needs no `engines=` registry at all — the
same structural absence `examples/deterministic/customer`/`examples/deterministic/waiter` demonstrate for their whole
actor. The one real vendor this pair exercises lives on `examples/llm-judged/delivery-person`'s `report-issue`
instead; see that app.py for `ENGINE`.

A NAME WITH A SPACE IS NOT A HOSTNAME. `HttpMailbox.deliver()`'s default addressing convention
lowercases a peer's own name and uses it as-is (`f"http://{to.lower()}:8080"`) — that works for
`"Waiter"` -> `waiter`, but `"Delivery Person"` -> `delivery person` is not a valid hostname.
`peers={"Delivery Person": "http://delivery-person:8080"}` below overrides the convention for
exactly this name, pointing at the k8s Service's own (hyphenated) name instead — `peers` exists
precisely for a case the lowercase-the-name convention can't cover on its own.

`GET /card` IS NOT A LIVE DISCOVERY DOOR. `ADR-PASH-0001` still holds — no runtime endpoint
recomputes another actor's doors on demand. `card.yaml` is `papeete-actor-synchronous-messaging
describe .`'s output, run exactly once at Docker build time (see `Dockerfile`); this route reads
that file's bytes once at startup and serves the same fixed dict back on every request, never
recomputing it.
"""
from pathlib import Path

import yaml
from papeete_actor_synchronous_messaging.actor import Actor

from papeete_actor_synchronous_messaging_http.mailbox import HttpMailbox
from notices import Notices

HERE = Path(__file__).resolve().parent
CARD = yaml.safe_load((HERE / "card.yaml").read_text())

ISSUE_SUBJECT = "the package arrived a day late and the box was crushed on one corner"
ISSUE_MEANS = ("tracking shows delivery at 11pm, not the promised morning slot; a photo taken "
              "on arrival shows the crushed corner")

_cell: dict = {}                     # filled with the actor after it boots — see below


def _trigger_claim() -> dict:
    """Open a real request/query exchange with the Delivery Person, over the network, and
    return what happened. This is where a real vendor's judgement is actually at stake —
    unlike `examples/deterministic/customer`'s `GET /order`, the reply's `accepted`/`remedy` can
    genuinely differ run to run once ENGINE names claude or openai."""
    buyer = _cell["actor"]
    ack = buyer.request(to="Delivery Person", action="report-issue", subject=ISSUE_SUBJECT,
                        means=ISSUE_MEANS)
    answer = {}
    if ack.get("accepted"):
        answer = buyer.query(to="Delivery Person", query="claim-status",
                             about=ack.get("claim_id"), asks="what happened with my claim?")
    return {
        "coupling": "Buyer -> Delivery Person over HTTP",
        "request": {"subject": ISSUE_SUBJECT, "means": ISSUE_MEANS},
        "ack": ack,
        "answer": answer,
    }


def _card_route() -> dict:
    return CARD


if __name__ == "__main__":
    notices = Notices()
    mailbox = HttpMailbox(
        peers={"Delivery Person": "http://delivery-person:8080"},
        routes={"/claim": _trigger_claim, "/card": _card_route})
    actor = Actor.from_card(
        HERE, mailbox=mailbox,
        actions={"delivery-notice": notices.delivery_notice},
        queries={"delivery-status": notices.delivery_status})
    _cell["actor"] = actor
    print(f"Buyer listening on :8080 — card {HERE}", flush=True)
    print("GET /claim triggers a real request + query exchange with the Delivery Person",
         flush=True)
    print("GET /card serves the composed card, baked in at build time", flush=True)
    mailbox.serve_forever()
