"""Batch 3 example: auto-generated rule IDs over shared use case."""

from fluxrules.domain import Rule
from fluxrules.engine.phreak import PhreakEngine

from shared_use_case import SHARED_FACTS, USE_CASE_NAME, complex_risk_condition


def main() -> None:
    print("=" * 80)
    print("17_id_generation.py")
    print(f"Use case: {USE_CASE_NAME}")
    print("=" * 80)

    print("Creating rules with auto-generated IDs...\n")

    # Rules without explicit IDs get auto-generated
    rule1 = Rule(
        name="auto_id_rule_1",
        domain="fraud_detection",
        condition_dsl=complex_risk_condition(),
        action="manual_review",
        priority=100,
    )

    rule2 = Rule(
        name="auto_id_rule_2",
        domain="compliance",
        condition_dsl=complex_risk_condition(),
        action="block",
        priority=100,
    )

    print(f"Rule 1: id={rule1.id}, name={rule1.name}")
    print(f"Rule 2: id={rule2.id}, name={rule2.name}\n")

    engine = PhreakEngine()
    engine.load_rules([rule1, rule2])

    for fact in SHARED_FACTS:
        result = engine.evaluate(fact)
        print(f"fact={fact['fact_id']} matched={result.fired_rules}")


if __name__ == "__main__":
    main()
