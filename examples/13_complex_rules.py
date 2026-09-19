"""Batch 3 example: complex nested conditions over shared use case."""

from fluxrules.engine.phreak import PhreakEngine

from shared_use_case import SHARED_FACTS, USE_CASE_NAME, build_shared_rules, complex_risk_condition


def main() -> None:
    print("=" * 80)
    print("13_complex_rules.py")
    print(f"Use case: {USE_CASE_NAME}")
    print("=" * 80)

    rules = build_shared_rules()
    engine = PhreakEngine()
    engine.load_rules(rules)

    print(f"Loaded {len(rules)} rules with complex nested conditions.\n")

    print("Complex DSL structure (8-condition tree with nested OR/AND/NOT):")
    import json
    dsl = complex_risk_condition()
    print(json.dumps(dsl, indent=2)[:500] + "...")  # Print first 500 chars
    print()

    for fact in SHARED_FACTS:
        result = engine.evaluate(fact)
        print(
            f"fact={fact['fact_id']} matched={result.fired_rules} actions={result.actions}"
        )


if __name__ == "__main__":
    main()
