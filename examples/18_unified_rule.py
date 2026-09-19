"""Batch 3 example: unified Rule class over shared use case."""

from fluxrules.domain import Rule
from fluxrules.engine.phreak import PhreakEngine

from shared_use_case import SHARED_FACTS, USE_CASE_NAME, complex_risk_condition


def main() -> None:
    print("=" * 80)
    print("18_unified_rule.py")
    print(f"Use case: {USE_CASE_NAME}")
    print("=" * 80)

    print("Creating unified Rule instances...\n")

    rule = Rule(
        name="unified_example",
        domain="fraud_detection",
        tags=frozenset(["tier_0", "cross_border"]),
        condition_dsl=complex_risk_condition(),
        action="manual_review",
        priority=100,
    )

    print(f"✅ Rule created:")
    print(f"  id={rule.id}")
    print(f"  name={rule.name}")
    print(f"  domain={rule.domain}")
    print(f"  tags={rule.tags}\n")

    engine = PhreakEngine()
    engine.load_rules([rule])

    for fact in SHARED_FACTS:
        result = engine.evaluate(fact)
        print(f"fact={fact['fact_id']} matched={result.fired_rules}")


if __name__ == "__main__":
    main()
