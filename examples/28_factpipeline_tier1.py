"""Batch 4 example: a tiered pipeline architecture.

Large ingestion pipelines are easier to own when they are split into tiers, each
a small ``FactPipeline`` with one job, chained with ``>>``:

- **tier 1, clean**: flatten the payload and fix field names and types;
- **tier 2, validate**: reject a record that is missing fields the rules need;
- **tier 3, enrich**: add derived fields the rules match on.

Each tier can be tested and changed on its own, and a failure names the tier
that raised. The output of tier 3 goes to the engine.
"""

from __future__ import annotations

from shared_use_case import USE_CASE_NAME

from fluxrules import F, Rule
from fluxrules.engine.phreak import PhreakEngine
from fluxrules.pipeline import (
    Defaults,
    FactPipeline,
    FieldType,
    Flatten,
    MapValues,
    Rename,
    Require,
)

TIER_1_CLEAN = FactPipeline(
    [
        Flatten(),
        Rename({"amount": ["payment.amount"], "country": ["customer.country"]}),
        FieldType({"amount": float}),
    ],
    name="tier1_clean",
)
TIER_2_VALIDATE = FactPipeline([Require(["event_id", "amount", "country"])], name="tier2_validate")
TIER_3_ENRICH = FactPipeline(
    [
        Defaults({"channel": "web"}),
        MapValues(str.upper, fields=["country"]),
    ],
    name="tier3_enrich",
)
PIPELINE = TIER_1_CLEAN >> TIER_2_VALIDATE >> TIER_3_ENRICH

RULE = Rule(
    id=1,
    name="large_payment_high_risk_country",
    conditions=(F("amount") > 2000) & (F("country").isin(["NG", "SN", "GH"])),
    action="manual_review",
)

EVENTS = [
    {"event_id": "txn-001", "payment": {"amount": "4200"}, "customer": {"country": "ng"}},
    {"event_id": "txn-002", "payment": {"amount": "950"}, "customer": {"country": "us"}},
    {"event_id": "txn-003", "payment": {}, "customer": {"country": "gh"}},
]


def main() -> None:
    print("=" * 80)
    print("28_factpipeline_tier1.py")
    print(f"Use case: {USE_CASE_NAME}")
    print("=" * 80)

    engine = PhreakEngine()
    engine.load_rules([RULE])

    event = EVENTS[0]
    after_1 = TIER_1_CLEAN(event)
    after_2 = TIER_2_VALIDATE(after_1)
    after_3 = TIER_3_ENRICH(after_2)
    print(f"\nraw:            {event}")
    print(f"after tier 1:   {after_1}")
    print(f"after tier 2:   {after_2}  (unchanged, validation only)")
    print(f"after tier 3:   {after_3}")

    print("\nAll three tiers chained with >>:")
    for raw in EVENTS:
        try:
            fact = PIPELINE(raw)
        except ValueError as exc:
            print(f"  {raw['event_id']}: rejected - {exc}")
            continue
        print(f"  {raw['event_id']}: matched={engine.evaluate(fact).fired_rules}")


if __name__ == "__main__":
    main()
