"""Batch 4 example: cross-fact relationships over shared use case."""

from fluxrules.engine.phreak import PhreakEngine

from shared_use_case import SHARED_FACTS, USE_CASE_NAME, build_shared_rules


def main() -> None:
    print("=" * 80)
    print("24_cross_fact_joins.py")
    print(f"Use case: {USE_CASE_NAME}")
    print("=" * 80)

    rules = build_shared_rules()
    engine = PhreakEngine()
    engine.load_rules(rules)

    print(f"Loaded {len(rules)} rules. Evaluating cross-fact patterns...\n")

    print("Cross-fact analysis (same rules, different facts):")
    for fact in SHARED_FACTS:
        result = engine.evaluate(fact)
        print(f"  {fact['fact_id']}: matched={result.fired_rules}")

    print("\nEach fact evaluated independently; no join operations.")


if __name__ == "__main__":
    main()
