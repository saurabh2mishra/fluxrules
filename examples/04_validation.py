"""Batch 1 example: validate nested DSL for one complex payment-risk use case."""

from shared_use_case import SHARED_FACTS, USE_CASE_NAME, build_shared_rules

from fluxrules.domain.dsl.validation import DSLValidationError, validate_dsl
from fluxrules.engine.phreak import PhreakEngine


def main() -> None:
    print("=" * 80)
    print("04_validation.py")
    print(f"Use case: {USE_CASE_NAME}")
    print("=" * 80)

    rules = build_shared_rules()

    print("validating nested condition trees")
    for rule in rules:
        validate_dsl(rule.condition_dsl)
        print(f"  validated rule={rule.name} id={rule.id}")

    invalid = {
        "type": "group",
        "op": "AND",
        "children": [
            {"type": "condition", "field": "amount", "op": "__bad_op__", "value": 5}
        ],
    }
    try:
        validate_dsl(invalid)
    except DSLValidationError as exc:
        print(f"  expected validation error: {exc}")

    engine = PhreakEngine()
    engine.load_rules(rules)
    for fact in SHARED_FACTS:
        result = engine.evaluate(fact)
        print(
            f"fact={fact['fact_id']} matched={result.fired_rules} actions={result.actions}"
        )


if __name__ == "__main__":
    main()
