"""Batch 4 example: load a batch of raw records with FactLoader.

``FactLoader`` reads records from a source, runs each one through a pipeline and
yields facts ready for the engine. With ``on_error="collect"`` a record that
fails the pipeline does not stop the batch: it goes to ``loader.dead_letter``
with the error, and loading continues.

The records here come from ``IterableSource``. ``CSVSource`` and ``JSONSource``
work the same way for files.
"""

from __future__ import annotations

from shared_use_case import USE_CASE_NAME, build_shared_rules

from fluxrules.engine.phreak import PhreakEngine
from fluxrules.pipeline import FactLoader, FactPipeline, FieldType, IterableSource, Require

# Raw rows as they might come from a CSV export: numbers are strings, and one
# row is missing its amount.
RAW_ROWS = [
    {
        "fact_id": "txn-001", "amount": "4200", "velocity_1h": "6",
        "chargeback_ratio": "0.14", "country": "NG", "ip_risk_score": "88",
        "device_age_days": "2", "account_age_days": "5",
        "email_domain": "newmail.example", "payment_method": "prepaid_card",
        "customer_tier": "standard", "currency": "USD",
        "tags": ["manual_review_candidate"],
    },
    {"fact_id": "txn-bad", "country": "US"},
    {
        "fact_id": "txn-003", "amount": "950", "velocity_1h": "1",
        "chargeback_ratio": "0.01", "country": "US", "ip_risk_score": "25",
        "device_age_days": "140", "account_age_days": "540",
        "email_domain": "trusted.example", "payment_method": "card",
        "customer_tier": "vip", "currency": "USD", "tags": [],
    },
]

NORMALIZE = FactPipeline(
    [
        Require(["fact_id", "amount"]),
        FieldType(
            {
                "amount": float,
                "velocity_1h": int,
                "chargeback_ratio": float,
                "ip_risk_score": int,
                "device_age_days": int,
                "account_age_days": int,
            }
        ),
    ],
    name="normalize_csv_rows",
)


def main() -> None:
    print("=" * 80)
    print("26_fact_loader.py")
    print(f"Use case: {USE_CASE_NAME}")
    print("=" * 80)

    engine = PhreakEngine()
    engine.load_rules(build_shared_rules())

    loader = FactLoader(source=IterableSource(RAW_ROWS), pipeline=NORMALIZE, on_error="collect")

    print(f"\nLoading {len(RAW_ROWS)} raw rows...\n")
    for fact in loader:
        result = engine.evaluate(fact)
        print(f"  {fact['fact_id']}: amount={fact['amount']!r} matched={result.fired_rules}")

    print(f"\nRows sent to dead_letter: {len(loader.dead_letter)}")
    for entry in loader.dead_letter:
        print(f"  {entry}")


if __name__ == "__main__":
    main()
