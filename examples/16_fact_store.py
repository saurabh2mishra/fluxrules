"""Batch 3 example: fact storage over shared use case."""

from fluxrules.engine.phreak import PhreakEngine

from shared_use_case import SHARED_FACTS, USE_CASE_NAME, build_shared_rules


def main() -> None:
    print("=" * 80)
    print("16_fact_store.py")
    print(f"Use case: {USE_CASE_NAME}")
    print("=" * 80)

    rules = build_shared_rules()
    engine = PhreakEngine()
    engine.load_rules(rules)

    print(f"Loaded {len(rules)} rules. Processing fact store...\n")

    for fact in SHARED_FACTS:
        result = engine.evaluate(fact)
        print(
            f"fact_id={fact['fact_id']} amount={fact['amount']} "
            f"matched={result.fired_rules}"
        )

    print(f"\nProcessed {len(SHARED_FACTS)} facts from fact store.")


if __name__ == "__main__":
    main()
