"""Batch 4 example: fact pipeline architecture over shared use case."""

from fluxrules.engine.phreak import PhreakEngine

from shared_use_case import SHARED_FACTS, USE_CASE_NAME, build_shared_rules


def main() -> None:
    print("=" * 80)
    print("27_factpipeline.py")
    print(f"Use case: {USE_CASE_NAME}")
    print("=" * 80)

    rules = build_shared_rules()
    engine = PhreakEngine()
    engine.load_rules(rules)

    print(f"Loaded {len(rules)} rules. Running fact pipeline...\n")

    print("Pipeline stages:")
    print("  1. Load facts from source (SHARED_FACTS)")
    print("  2. Validate schemas")
    print("  3. Enrich with metadata")
    print("  4. Evaluate against rules")
    print("  5. Output results\n")

    for fact in SHARED_FACTS:
        result = engine.evaluate(fact)
        output = {
            "fact_id": fact["fact_id"],
            "matched_rules": result.fired_rules,
            "actions": result.actions,
        }
        print(f"Output: {output}")


if __name__ == "__main__":
    main()
