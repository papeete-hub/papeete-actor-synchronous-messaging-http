"""The Waiter, deployed for real: a container, an HttpMailbox, and one operator-facing route.

STDLIB ONLY, on purpose — the same choice every small actor in this ecosystem already makes
(`papeete-actor`'s `car-inspector`, `papeete-deploy`'s own customer/waiter demo). No framework
to pin, no framework to explain to a reader for a container this small.

THE ENGINE IS SCRIPTED, DELIBERATELY. This is a worked example of DEPLOYMENT, not of judgement
— the same `ScriptedEngine` the core package's own conformance suite runs on, so this container
needs no key and no vendor to prove the shape holds over a real socket.

`GET /card` IS NOT A LIVE DISCOVERY DOOR. `ADR-PASH-0001` still holds — no runtime endpoint
recomputes another actor's doors on demand. `card.yaml` is `papeete-actor-synchronous-messaging
describe .`'s output, run exactly once at Docker build time (see `Dockerfile`); this route reads
that file's bytes once at startup and serves the same fixed dict back on every request, never
recomputing it. It exists for a human at a browser, not for another actor's own resolution.
"""
from pathlib import Path

import yaml
from papeete_actor_synchronous_messaging.actor import Actor
from papeete_actor_synchronous_messaging.engine import ScriptedEngine

from papeete_actor_synchronous_messaging_http.mailbox import HttpMailbox
from order_book import OrderBook

HERE = Path(__file__).resolve().parent
CARD = yaml.safe_load((HERE / "card.yaml").read_text())

RULES = [
    ("verb: request", {"accepted": True,
                       "because": "the table exists and the dish is on tonight's menu."}),
    ("verb: query", {"says": "answering from the order book."}),
]


def _card_route() -> dict:
    return CARD


if __name__ == "__main__":
    book = OrderBook()
    mailbox = HttpMailbox(routes={"/card": _card_route})
    actor = Actor.from_card(HERE, ScriptedEngine(RULES), mailbox=mailbox, work=book.work)
    print(f"Waiter listening on :8080 — card {HERE}", flush=True)
    print("GET /card serves the composed card, baked in at build time", flush=True)
    mailbox.serve_forever()
