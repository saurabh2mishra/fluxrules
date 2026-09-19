"""Batch 2 example: engine patterns over shared use case."""

from fluxrules.engine.phreak import PhreakEngine

from shared_use_case import SHARED_FACTS, USE_CASE_NAME, build_shared_rules


def main() -> None:
    print("=" * 80)
    print("09_custom_engines.py")
    print(f"Use case: {USE_CASE_NAME}")
    print("=" * 80)

    rules = build_shared_rules()

    engine = PhreakEngine()
    engine.load_rules(rules)

    print(f"Loaded {len(rules)} rules with PhreakEngine.\n")

    for fact in SHARED_FACTS:
        result = engine.evaluate(fact)
        print(
            f"fact={fact['fact_id']} matched={result.fired_rules} actions={result.actions}"
        )

    print("\nPhreakEngine uses lazy evaluation (PHREAK algorithm).")


if __name__ == "__main__":
    main()
