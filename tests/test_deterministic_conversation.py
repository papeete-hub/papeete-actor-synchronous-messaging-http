"""The `confirm-substitution` conversation, over real sockets — a request that triggers a
second request, whose reply changes the answering actor's own state, discovered later by query.

WHAT THIS FILE IS FOR. `test_http_mailbox.py` proves the wire mechanism against synthetic doors.
This file proves the same mechanism against `examples/deterministic`'s REAL business logic
(`decide.py`, `order_book.py`) — no engine anywhere on either card (ADR-PAS-0012) — driving the
one worked conversation in this repo where opening a door does not just answer, it reaches back
out to a second actor before it can:

    Waiter --(request: confirm-substitution)--> Customer
                Customer --(query:   order-status)--> Waiter    # 1. knowledge it doesn't hold
                Customer --(request: take-order  )--> Waiter    # 2. work it may not do itself
                Customer records a decision, quoting the Waiter's own replies into it
    Waiter --(query: substitution-decision)--> Customer          # the new state, discovered

Three hops, two actors, each real dict crossing a real socket and surviving JSON round-tripping
— the one thing `examples/deterministic/customer/app.py`'s own `GET /order` trigger never exercises,
since it only ever opens `take-order`/`order-status` in the other direction.

REAL CARDS, LOADED FROM DISK. `Actor.from_card(CUSTOMER, ...)` reads
`examples/deterministic/customer/actor.yaml` and its siblings exactly the way the deployed
container does — unlike `test_http_mailbox.py`'s hand-built `Card`, a change to either actor's
own YAML that broke this conversation would fail HERE.
"""
from __future__ import annotations

import importlib.util
import threading
from pathlib import Path

import pytest

from papeete_actor_synchronous_messaging.actor import Actor

from papeete_actor_synchronous_messaging_http.mailbox import HttpMailbox

from conftest import free_port, wait_until_listening

EXAMPLES = Path(__file__).resolve().parent.parent / "examples" / "deterministic"
CUSTOMER, WAITER = EXAMPLES / "customer", EXAMPLES / "waiter"


def _from_example(folder: Path, module: str, attr: str):
    """Import an example folder's own code, by path — `examples/` is a deploy tree, not an
    installed package, the same reason `papeete-actor-synchronous-messaging`'s own
    `claim_conversation.py` imports its worked examples this way rather than a plain `import`."""
    spec = importlib.util.spec_from_file_location(f"{folder.name}_{module}", folder / f"{module}.py")
    loaded = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(loaded)
    return getattr(loaded, attr)


Decisions = _from_example(CUSTOMER, "decide", "Decisions")
OrderBook = _from_example(WAITER, "order_book", "OrderBook")

TABLE = 5
SUBJECT = "the wild mushroom risotto"          # what the table originally ordered — on the menu
SUBSTITUTE = "barley risotto"                  # same naive category, and Customer's own known list


@pytest.fixture
def customer_and_waiter():
    """Two `Actor`s booted from their REAL folders, each on its own `HttpMailbox`, each serving
    on a real `127.0.0.1` port — `peers` stands in for the name-is-hostname convention a real
    cluster's DNS would otherwise supply (`ADR-PASH-0004`'s own docstring makes the same point)."""
    customer_port, waiter_port = free_port(), free_port()

    customer_box = HttpMailbox(host="127.0.0.1", port=customer_port,
                               peers={"Waiter": f"http://127.0.0.1:{waiter_port}"})
    waiter_box = HttpMailbox(host="127.0.0.1", port=waiter_port,
                             peers={"Customer": f"http://127.0.0.1:{customer_port}"})

    decisions = Decisions()
    book = OrderBook()

    customer = Actor.from_card(
        CUSTOMER, mailbox=customer_box,
        actions={"confirm-substitution": decisions.confirm_substitution},
        queries={"substitution-decision": decisions.substitution_decision})
    waiter = Actor.from_card(
        WAITER, mailbox=waiter_box,
        actions={"take-order": book.take_order, "give-table": book.give_table},
        queries={"order-status": book.order_status})

    threads = [threading.Thread(target=box.serve_forever, daemon=True)
               for box in (customer_box, waiter_box)]
    for t in threads:
        t.start()
    wait_until_listening(customer_port)
    wait_until_listening(waiter_port)

    yield customer, waiter, decisions, book

    customer_box.shutdown()
    waiter_box.shutdown()


def test_a_request_the_answerer_cannot_finish_alone_reaches_back_out(customer_and_waiter):
    """`confirm-substitution` is the trigger; `substitution-decision` is where the new state,
    built out of a second actor's own reply, is discovered — never inside the ack itself."""
    customer, waiter, decisions, book = customer_and_waiter

    # 1. THE ORIGINAL ORDER, ALREADY ON THE WAITER'S OWN BOOK — the thing `confirm-substitution`
    #    is a proposed change around. `decide.py`'s own knowledge step reads the book back,
    #    mid-decision, without being told this order's id — it asks what the book holds overall.
    original_ack = customer.request(to="Waiter", action="take-order", table_number=TABLE,
                                    subject=SUBJECT,
                                    means="the standard order, no allergies flagged.")
    assert original_ack["accepted"] is True
    original_order_id = original_ack["order_id"]

    # 2. THE TRIGGER — I act with the Customer by opening its own `confirm-substitution` door;
    #    everything from here on is the CUSTOMER'S own doing, not mine. `from_="Waiter"` matters:
    #    `confirm_substitution` calls back whoever opened this exchange, so the caller has to be
    #    the same Waiter Actor that is actually listening, not a stand-in name.
    decision_ack = waiter.request(to="Customer", action="confirm-substitution",
                                  table_number=TABLE, original_dish=SUBJECT, subject=SUBSTITUTE,
                                  means="the kitchen ran out; this is the closest thing left.")
    assert decision_ack["accepted"] is True
    decision_id = decision_ack["decision_id"]

    # 3. THE NEW STATE, ASKED FOR — nothing above told the caller what got written; only a
    #    fresh query against the CUSTOMER (the actor whose state actually changed) does.
    found = waiter.query(to="Customer", query="substitution-decision", about=decision_id,
                         asks="what did you decide, and what did the kitchen end up cooking?")
    assert found["says"] == f"{decision_id}: on record — '{SUBSTITUTE}'"
    entry = found["decision"]
    assert entry["subject"] == SUBSTITUTE
    assert entry["proposed_by"] == "Waiter"

    # 4. THE STATE CHANGE IS NOT A COPY OF WHAT CUSTOMER SENT — it is THE WAITER'S OWN REPLIES,
    #    quoted back verbatim, proving both callbacks actually happened rather than being
    #    assumed. `waiter_said` is the KNOWLEDGE step (order-status, asked before the swap) —
    #    the original order was already on the book by then.
    assert entry["waiter_said"]["orders"] == [original_order_id]

    # `waiter_ack` is the WORK step (take-order for the substitute) — a SECOND, independent
    # order, never a rewrite of the first: Customer cannot write the Waiter's own book, it can
    # only ask, and the Waiter's own `take_order` always appends rather than replaces.
    assert entry["waiter_ack"]["accepted"] is True
    substitute_order_id = entry["waiter_ack"]["order_id"]
    assert substitute_order_id != original_order_id

    # 5. AND THE WAITER'S OWN BOOK AGREES — the SAME conversation, seen from the other side.
    assert book.entries[original_order_id]["subject"] == SUBJECT
    assert book.entries[substitute_order_id]["subject"] == SUBSTITUTE
    assert book.entries[substitute_order_id]["opened_by"] == "Customer"


def test_a_denied_substitution_never_reaches_the_waiter_at_all(customer_and_waiter):
    """The fact-check in `decide.py` runs BEFORE either callback — a substitute of the wrong
    kind never touches the Waiter's order book, and never even asks it anything."""
    customer, waiter, decisions, book = customer_and_waiter

    decision_ack = waiter.request(to="Customer", action="confirm-substitution",
                                  table_number=TABLE, original_dish=SUBJECT,
                                  subject="a green salad",             # wrong category
                                  means="the kitchen ran out.")
    assert decision_ack == {"accepted": False,
                            "because": "'a green salad' is not the same kind of dish as "
                                       f"'{SUBJECT}'"}
    assert book.entries == {}, "a refused substitution must never write to the Waiter's book"
    assert decisions.entries == {}, "nor should it leave a decision behind to ask about later"
