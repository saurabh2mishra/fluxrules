"""Batch 1 example: nested clauses for one complex payment-risk use case."""

from shared_use_case import SHARED_FACTS, USE_CASE_NAME, complex_risk_condition

from fluxrules.domain import Rule
from fluxrules.engine.phreak import PhreakEngine


def main() -> None:
    print("=" * 80)
    print("02_complex_conditions.py")
    print(f"Use case: {USE_CASE_NAME}")
    print("=" * 80)

    rule = Rule(
        id=201,
        name="nested_triage_rule",
        condition_dsl=complex_risk_condition(),
        action="manual_review",
        priority=20,
        domain="fraud_detection",
    )
    engine = PhreakEngine()
    engine.load_rules([rule])

    print("Nested branch 1: country in high-risk list OR ip_risk_score >= 70")
    print("Nested branch 2: device_age_days < 7 OR account_age_days < 14")
    print("Nested branch 3: NOT email_domain ends_with trusted.example")

    for fact in SHARED_FACTS:
        result = engine.evaluate(fact)
        print(
            f"fact={fact['fact_id']} matched={result.fired_rules} actions={result.actions}"
        )


if __name__ == "__main__":
    main()
