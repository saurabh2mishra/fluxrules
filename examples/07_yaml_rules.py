"""Batch 2 example: YAML rule definition over shared use case."""

import yaml

from fluxrules.domain import Rule
from fluxrules.engine.phreak import PhreakEngine

from shared_use_case import SHARED_FACTS, USE_CASE_NAME, complex_risk_condition


def main() -> None:
    print("=" * 80)
    print("07_yaml_rules.py")
    print(f"Use case: {USE_CASE_NAME}")
    print("=" * 80)

    yaml_rule_str = """
name: "cross_border_risk_triage"
domain: "fraud_detection"
tags:
  - "tier_0"
  - "cross_border"
action: "manual_review"
priority: 100
"""
    yaml_data = yaml.safe_load(yaml_rule_str)

    rule = Rule(
        name=yaml_data["name"],
        domain=yaml_data["domain"],
        tags=frozenset(yaml_data["tags"]),
        action=yaml_data["action"],
        priority=yaml_data["priority"],
        condition_dsl=complex_risk_condition(),
    )

    engine = PhreakEngine()
    engine.load_rules([rule])

    print(f"Loaded 1 rule from YAML. Evaluating facts...\n")

    for fact in SHARED_FACTS:
        result = engine.evaluate(fact)
        print(
            f"fact={fact['fact_id']} matched={result.fired_rules} actions={result.actions}"
        )


if __name__ == "__main__":
    main()
