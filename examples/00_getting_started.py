"""Batch 1 example: quick start with one complex payment-risk use case.

This file uses the shared dataset and a nested condition with 8 checks.
"""

from shared_use_case import SHARED_FACTS, USE_CASE_NAME, complex_risk_condition

from fluxrules.domain import Rule
from fluxrules.engine.phreak import PhreakEngine


def main() -> None:
    print("=" * 80)
    print("00_getting_started.py")
    print(f"Use case: {USE_CASE_NAME}")
    print("=" * 80)

    engine = PhreakEngine()
    rule = Rule(
        id=1,
        name="manual_review_gate",
        condition_dsl=complex_risk_condition(),
        action="manual_review",
        priority=20,
        domain="fraud_detection",
    )
    engine.load_rules([rule])

    for fact in SHARED_FACTS:
        result = engine.evaluate(fact)
        print(
            f"fact={fact['fact_id']} matched={result.fired_rules} actions={result.actions}"
        )


if __name__ == "__main__":
    main()
