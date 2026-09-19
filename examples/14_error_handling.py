"""Batch 3 example: validation and error handling over shared use case."""

from fluxrules.domain.dsl.validation import DSLValidationError, validate_dsl
from fluxrules.engine.phreak import PhreakEngine

from shared_use_case import SHARED_FACTS, USE_CASE_NAME, build_shared_rules


def main() -> None:
    print("=" * 80)
    print("14_error_handling.py")
    print(f"Use case: {USE_CASE_NAME}")
    print("=" * 80)

    rules = build_shared_rules()
    engine = PhreakEngine()
    engine.load_rules(rules)

    print(f"Loaded {len(rules)} rules. Testing error handling...\n")

    # Validate all rules
    for rule in rules:
        try:
            validate_dsl(rule.condition_dsl)
            print(f"✅ Rule {rule.id}: valid DSL")
        except DSLValidationError as e:
            print(f"❌ Rule {rule.id}: {e}")

    print()

    # Evaluate with error handling
    for fact in SHARED_FACTS:
        try:
            result = engine.evaluate(fact)
            print(
                f"fact={fact['fact_id']} matched={result.fired_rules} actions={result.actions}"
            )
        except Exception as e:
            print(f"Error evaluating {fact['fact_id']}: {e}")


if __name__ == "__main__":
    main()
