"""The Customer, deployed for real: a container, an HttpMailbox, and one operator-facing route.

STDLIB ONLY, on purpose — the same choice every small actor in this ecosystem already makes.

`GET /order` IS NOT A DOOR. It is this deployment's own trigger, answered by `HttpMailbox`'s one
extension point (`routes`) — a human or a script hitting it makes the Customer open a real
`request`/`query` exchange against the Waiter, over the network, and returns what came back.
Nothing here is protocol; it is the operator's window onto a conversation the membrane governs
one layer down. `"Waiter"` and its door ids (`take-order`, `order-status`) are this file's own
business knowledge, the same way `decide.py` already knows them — nothing here resolves or
gates that coupling.
"""
from pathlib import Path

from papeete_actor_synchronous_messaging.actor import Actor
from papeete_actor_synchronous_messaging.engine import ScriptedEngine

from papeete_actor_synchronous_messaging_http.mailbox import HttpMailbox
from decide import Decisions

HERE = Path(__file__).resolve().parent

RULES = [
    ("verb: request", {"accepted": True,
                       "because": "a barley risotto is close enough to what was ordered."}),
    ("verb: query", {"says": "answering from my own records."}),
]

SUBJECT = "table 5: the wild mushroom risotto"
MEANS = "the standard order, no allergies flagged."

_cell: dict = {}                     # filled with the actor after it boots — see below


def _trigger_order() -> dict:
    """Open a real request/query exchange with the Waiter, over the network, and return what
    happened."""
    customer = _cell["actor"]
    ack = customer.request(to="Waiter", action="take-order", subject=SUBJECT, means=MEANS)
    answer = customer.query(to="Waiter", query="order-status", about=ack.get("order"),
                            asks="what became of the order I placed?")
    return {
        "coupling": "Customer -> Waiter over HTTP",
        "request": {"subject": SUBJECT, "means": MEANS},
        "ack": ack,
        "answer": answer,
    }


if __name__ == "__main__":
    decisions = Decisions()
    mailbox = HttpMailbox(routes={"/order": _trigger_order})
    actor = Actor.from_card(HERE, ScriptedEngine(RULES), mailbox=mailbox, work=decisions.work)
    _cell["actor"] = actor
    print(f"Customer listening on :8080 — card {HERE}", flush=True)
    print("GET /order triggers a real request + query exchange with the Waiter", flush=True)
    mailbox.serve_forever()
