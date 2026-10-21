"""Batch 4 example: nested facts, flattened before evaluation.

The engine matches flat key-value facts. It does not walk into nested
dictionaries. Payment events usually arrive nested, so flatten them first with
the ``Flatten`` transform, which turns ``{"payment": {"amount": 4200}}`` into
``{"payment.amount": 4200}``. Rules then refer to the dotted names.
"""

from __future__ import annotations

from shared_use_case import USE_CASE_NAME

from fluxrules import F, Rule
from fluxrules.engine.phreak import PhreakEngine
from fluxrules.pipeline import FactPipeline, Flatten

NESTED_EVENTS = [
    {
        "event_id": "txn-001",
        "payment": {"amount": 4200, "method": "prepaid_card"},
        "customer": {"country": "NG", "account": {"age_days": 5}},
    },
    {
        "event_id": "txn-002",
        "payment": {"amount": 950, "method": "card"},
        "customer": {"country": "US", "account": {"age_days": 540}},
    },
]

RULE = Rule(
    id=1,
    name="large_payment_new_account",
    conditions=(
        (F("payment.amount") > 2000)
        & (F("customer.account.age_days") < 14)
        & (F("payment.method").isin(["crypto", "prepaid_card"]))
    ),
    action="manual_review",
)


def main() -> None:
    print("=" * 80)
    print("25_nested_facts.py")
    print(f"Use case: {USE_CASE_NAME}")
    print("=" * 80)

    flatten = FactPipeline([Flatten()], name="flatten")
    engine = PhreakEngine()
    engine.load_rules([RULE])

    for event in NESTED_EVENTS:
        flat = flatten(event)
        result = engine.evaluate(flat)
        print(f"\n{event['event_id']} raw:  {event}")
        print(f"{event['event_id']} flat: {flat}")
        print(f"  matched={result.fired_rules} actions={result.actions}")

    # A nested fact passed without flattening has no "payment.amount" key, so
    # the rule cannot match it.
    unflattened = engine.evaluate(NESTED_EVENTS[0])
    print(f"\ntxn-001 without Flatten -> matched={unflattened.fired_rules}")


if __name__ == "__main__":
    main()
