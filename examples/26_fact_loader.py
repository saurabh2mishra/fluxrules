"""Batch 4 example: fact loading and batch processing over shared use case."""

from fluxrules.engine.phreak import PhreakEngine

from shared_use_case import SHARED_FACTS, USE_CASE_NAME, build_shared_rules


def main() -> None:
    print("=" * 80)
    print("26_fact_loader.py")
    print(f"Use case: {USE_CASE_NAME}")
    print("=" * 80)

    rules = build_shared_rules()
    engine = PhreakEngine()
    engine.load_rules(rules)

    print(f"Loading {len(SHARED_FACTS)} facts...\n")

    results = []
    for fact in SHARED_FACTS:
        result = engine.evaluate(fact)
        results.append((fact['fact_id'], result.fired_rules))
        print(f"Loaded & evaluated: {fact['fact_id']}")

    print(f"\n✅ Processed {len(results)} facts total")


if __name__ == "__main__":
    main()
