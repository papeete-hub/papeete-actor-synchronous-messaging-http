"""The Waiter, deployed for real: a container, an HttpMailbox, and one operator-facing route.

STDLIB ONLY, on purpose — the same choice every small actor in this ecosystem already makes
(`papeete-actor`'s `car-inspector`, `papeete-deploy`'s own customer/waiter demo). No framework
to pin, no framework to explain to a reader for a container this small.

NO ENGINE, NO VENDOR, NO KEY (ADR-PAS-0012). This actor's own doors — `take-order`, `give-table`,
`order-status` — are all plain checks against `order_book.py`'s own state (a table roster, a
menu, who is seated), not judgement calls; nothing here needs a vendor's opinion to prove the
shape holds over a real socket.

`GET /card` IS NOT A LIVE DISCOVERY DOOR. `ADR-PASH-0001` still holds — no runtime endpoint
recomputes another actor's doors on demand. `card.yaml` is `papeete-actor-synchronous-messaging
describe .`'s output, run exactly once at Docker build time (see `Dockerfile`); this route reads
that file's bytes once at startup and serves the same fixed dict back on every request, never
recomputing it. It exists for a human at a browser, not for another actor's own resolution.

`CUSTOMER_URL`, OPTIONAL, OVERRIDES `HttpMailbox`'s NAME-IS-HOSTNAME CONVENTION — needed here
because `confirm-substitution`/`substitution-decision` (the Customer's own doors) are opened FROM
the Waiter, the reverse direction of `/order`; see `customer/app.py`'s own docstring for why this
override exists at all (`ADR-PD-0004`'s product-scoped `namePrefix`, `papeete-deploy` >= 0.2.0).
"""
import os
from pathlib import Path

import yaml
from papeete_actor_synchronous_messaging.actor import Actor
from papeete_observability import configure

from papeete_actor_synchronous_messaging_http.mailbox import HttpMailbox
from order_book import OrderBook

HERE = Path(__file__).resolve().parent
CARD = yaml.safe_load((HERE / "card.yaml").read_text())

PEERS = {"Customer": os.environ["CUSTOMER_URL"]} if "CUSTOMER_URL" in os.environ else None


def _card_route() -> dict:
    return CARD


if __name__ == "__main__":
    configure()                        # OTLP tracing/metrics/logs — see papeete-observability
    book = OrderBook()
    mailbox = HttpMailbox(routes={"/card": _card_route}, peers=PEERS)
    actor = Actor.from_card(
        HERE, mailbox=mailbox,
        actions={"take-order": book.take_order, "give-table": book.give_table},
        queries={"order-status": book.order_status})
    print(f"Waiter listening on :8080 — card {HERE}", flush=True)
    print("GET /card serves the composed card, baked in at build time", flush=True)
    mailbox.serve_forever()
