"""Batch 2 example: complete rules loaded from a YAML file.

``payment_risk_rules.yaml`` holds every part of each rule, conditions included,
so rules can be reviewed and changed without touching Python code. The script:

1. loads the file with ``load_rules_from_yaml``;
2. turns each entry into a ``Rule`` with ``Rule.model_validate_yaml``;
3. evaluates the shared facts;
4. checks that the YAML triage rule decides every fact the same way as the
   F-built ``complex_risk_condition()``.
"""

from __future__ import annotations

from pathlib import Path

from shared_use_case import SHARED_FACTS, USE_CASE_NAME, complex_risk_condition

from fluxrules import Rule
from fluxrules.adapters.loaders.yaml_loader import load_rules_from_yaml
from fluxrules.engine.phreak import PhreakEngine

RULES_FILE = Path(__file__).parent / "payment_risk_rules.yaml"


def main() -> None:
    print("=" * 80)
    print("07_yaml_rules.py")
    print(f"Use case: {USE_CASE_NAME}")
    print("=" * 80)

    # persist=False keeps the rules in memory instead of writing them to a database.
    rows = load_rules_from_yaml(str(RULES_FILE))
    rules = [Rule.model_validate_yaml({**row, "persist": False}) for row in rows]

    print(f"\nLoaded {len(rules)} rules from {RULES_FILE.name}:")
    for rule in rules:
        print(f"  id={rule.id} {rule.name} priority={rule.priority} action={rule.action}")

    engine = PhreakEngine()
    engine.load_rules(rules)

    print("\nEvaluating the shared facts:")
    for fact in SHARED_FACTS:
        result = engine.evaluate(fact)
        print(f"  {fact['fact_id']}: matched={result.fired_rules} actions={result.actions}")

    # The same triage rule written in Python with F must agree on every fact.
    yaml_rule = next(r for r in rules if r.name == "cross_border_risk_triage")
    f_rule = Rule(
        id=yaml_rule.id,
        name=yaml_rule.name,
        conditions=complex_risk_condition(),
        action=yaml_rule.action,
        persist=False,
    )
    yaml_engine, f_engine = PhreakEngine(), PhreakEngine()
    yaml_engine.load_rules([yaml_rule])
    f_engine.load_rules([f_rule])

    print("\nYAML rule vs F-built rule:")
    for fact in SHARED_FACTS:
        from_yaml = yaml_engine.evaluate(fact).fired_rules
        from_f = f_engine.evaluate(fact).fired_rules
        assert from_yaml == from_f, f"{fact['fact_id']}: {from_yaml} != {from_f}"
        print(f"  {fact['fact_id']}: yaml={from_yaml} f={from_f} agree")


if __name__ == "__main__":
    main()
