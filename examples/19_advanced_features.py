"""Batch 3 example: advanced features over shared use case."""

from fluxrules.engine.phreak import PhreakEngine

from shared_use_case import SHARED_FACTS, USE_CASE_NAME, build_shared_rules


def main() -> None:
    print("=" * 80)
    print("19_advanced_features.py")
    print(f"Use case: {USE_CASE_NAME}")
    print("=" * 80)

    rules = build_shared_rules()
    engine = PhreakEngine()
    engine.load_rules(rules)

    print(f"Loaded {len(rules)} rules with advanced features...\n")

    total_fired = 0
    for fact in SHARED_FACTS:
        result = engine.evaluate(fact)
        total_fired += len(result.fired_rules)
        print(
            f"fact={fact['fact_id']} "
            f"matched={len(result.fired_rules)} rules, "
            f"latency={result.latency_ms}ms"
        )

    print(f"\nTotal rules fired across all facts: {total_fired}")


if __name__ == "__main__":
    main()
