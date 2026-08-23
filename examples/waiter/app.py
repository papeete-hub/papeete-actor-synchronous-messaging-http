"""The Waiter, deployed for real: a container, an HttpMailbox, and nothing else.

STDLIB ONLY, on purpose — the same choice every small actor in this ecosystem already makes
(`papeete-actor`'s `car-inspector`, `papeete-deploy`'s own customer/waiter demo). No framework
to pin, no framework to explain to a reader for a container this small.

THE ENGINE IS SCRIPTED, DELIBERATELY. This is a worked example of DEPLOYMENT, not of judgement
— the same `ScriptedEngine` the core package's own conformance suite runs on, so this container
needs no key and no vendor to prove the shape holds over a real socket.
"""
from pathlib import Path

from papeete_actor_synchronous_messaging.actor import Actor
from papeete_actor_synchronous_messaging.engine import ScriptedEngine

from papeete_actor_synchronous_messaging_http.mailbox import HttpMailbox
from order_book import OrderBook

HERE = Path(__file__).resolve().parent

RULES = [
    ("verb: request", {"accepted": True,
                       "because": "the table exists and the dish is on tonight's menu."}),
    ("verb: query", {"says": "answering from the order book."}),
]

if __name__ == "__main__":
    book = OrderBook()
    mailbox = HttpMailbox()
    actor = Actor.from_card(HERE, ScriptedEngine(RULES), mailbox=mailbox, work=book.work)
    print(f"Waiter listening on :8080 — card {HERE}", flush=True)
    mailbox.serve_forever()
