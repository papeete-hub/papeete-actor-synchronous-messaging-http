"""The Customer, deployed for real: a container, an HttpMailbox, and one operator-facing route.

STDLIB ONLY, on purpose — the same choice every small actor in this ecosystem already makes.

`GET /order` IS NOT A DOOR. It is this deployment's own trigger, answered by `HttpMailbox`'s one
extension point (`routes`) — a human or a script hitting it makes the Customer open a real
`request`/`query` exchange against the Waiter, over the network, and returns what came back.
Nothing here is protocol; it is the operator's window onto a conversation the membrane governs
one layer down. `"Waiter"` and its door ids (`take-order`, `order-status`) are this file's own
business knowledge, the same way `decide.py` already knows them — nothing here resolves or
gates that coupling.

`GET /card` IS NOT A LIVE DISCOVERY DOOR EITHER. `ADR-PASH-0001` still holds — no runtime
endpoint recomputes another actor's doors on demand. `card.yaml` is `papeete-actor-synchronous-
messaging describe .`'s output, run exactly once at Docker build time (see `Dockerfile`); this
route reads that file's bytes once at startup and serves the same fixed dict back on every
request, never recomputing it. It exists for a human at a browser, not for another actor's own
resolution.

`WAITER_URL`, OPTIONAL, OVERRIDES `HttpMailbox`'s NAME-IS-HOSTNAME CONVENTION. Under
`papeete-deploy` >= 0.2.0 (`ADR-PD-0004`), every k8s object it applies is renamed with a
product-scoped prefix (`waiter` -> `table-service-waiter`) — a literal string value like a peer's
own hostname is exactly what that `namePrefix` transform structurally cannot see, so the Waiter's
own `Service` is no longer reachable at the bare name `deliver()` would otherwise guess. `peers`
(see `HttpMailbox`'s own docstring) already exists for precisely this case; this deployment's own
`deploy/k8s/base/deployment.yaml` sets `WAITER_URL` to the real, product-prefixed base URL. Unset
(e.g. under Compose, where names stay bare), `HttpMailbox`'s own convention is untouched.
"""
import os
from pathlib import Path

import yaml
from papeete_actor_synchronous_messaging.actor import Actor
from papeete_observability import configure

from papeete_actor_synchronous_messaging_http.mailbox import HttpMailbox
from decide import Decisions

HERE = Path(__file__).resolve().parent
CARD = yaml.safe_load((HERE / "card.yaml").read_text())

PEERS = {"Waiter": os.environ["WAITER_URL"]} if "WAITER_URL" in os.environ else None

TABLE_NUMBER = 5
SUBJECT = "the wild mushroom risotto"
MEANS = "the standard order, no allergies flagged."

_cell: dict = {}                     # filled with the actor after it boots — see below


def _trigger_order() -> dict:
    """Open a real request/query exchange with the Waiter, over the network, and return what
    happened."""
    customer = _cell["actor"]
    ack = customer.request(to="Waiter", action="take-order", table_number=TABLE_NUMBER,
                           subject=SUBJECT, means=MEANS)
    answer = customer.query(to="Waiter", query="order-status", about=ack.get("order_id"),
                            asks="what became of the order I placed?")
    return {
        "coupling": "Customer -> Waiter over HTTP",
        "request": {"table_number": TABLE_NUMBER, "subject": SUBJECT, "means": MEANS},
        "ack": ack,
        "answer": answer,
    }


def _card_route() -> dict:
    return CARD


if __name__ == "__main__":
    configure()                        # OTLP tracing/metrics/logs — see papeete-observability
    decisions = Decisions()
    mailbox = HttpMailbox(routes={"/order": _trigger_order, "/card": _card_route}, peers=PEERS)
    actor = Actor.from_card(
        HERE, mailbox=mailbox,
        actions={"confirm-substitution": decisions.confirm_substitution},
        queries={"substitution-decision": decisions.substitution_decision})
    _cell["actor"] = actor
    print(f"Customer listening on :8080 — card {HERE}", flush=True)
    print("GET /order triggers a real request + query exchange with the Waiter", flush=True)
    print("GET /card serves the composed card, baked in at build time", flush=True)
    mailbox.serve_forever()
