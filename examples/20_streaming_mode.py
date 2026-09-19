"""Batch 3 example: streaming evaluation over shared use case."""

from fluxrules.engine.phreak import PhreakEngine

from shared_use_case import SHARED_FACTS, USE_CASE_NAME, build_shared_rules


def main() -> None:
    print("=" * 80)
    print("20_streaming_mode.py")
    print(f"Use case: {USE_CASE_NAME}")
    print("=" * 80)

    rules = build_shared_rules()
    engine = PhreakEngine()
    engine.load_rules(rules)

    print(f"Streaming evaluation of {len(SHARED_FACTS)} facts...\n")

    for idx, fact in enumerate(SHARED_FACTS, 1):
        result = engine.evaluate(fact)
        print(
            f"[{idx}/{len(SHARED_FACTS)}] fact={fact['fact_id']} "
            f"matched={result.fired_rules}"
        )

    print(f"\nStreaming complete: processed {len(SHARED_FACTS)} facts.")


if __name__ == "__main__":
    main()
