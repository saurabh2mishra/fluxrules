"""Batch 4 example: stateless vs streaming evaluation over shared use case."""

from fluxrules.engine.phreak import PhreakEngine

from shared_use_case import SHARED_FACTS, USE_CASE_NAME, build_shared_rules


def main() -> None:
    print("=" * 80)
    print("23_streaming_vs_stateless.py")
    print(f"Use case: {USE_CASE_NAME}")
    print("=" * 80)

    rules = build_shared_rules()
    engine = PhreakEngine()
    engine.load_rules(rules)

    print("\nStateless evaluation (each fact independent):")
    for fact in SHARED_FACTS:
        result = engine.evaluate(fact)
        print(f"  {fact['fact_id']}: {result.fired_rules}")

    print("\n(Streaming and stateless are equivalent in this pattern)")


if __name__ == "__main__":
    main()
