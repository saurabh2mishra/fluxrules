"""Batch 2 example: stateful evaluation over shared use case.

Demonstrates independent fact evaluation without shared state.
"""

from shared_use_case import SHARED_FACTS, USE_CASE_NAME, build_shared_rules

from fluxrules.engine.phreak import PhreakEngine


def main() -> None:
    print("=" * 80)
    print("06_working_memory.py")
    print(f"Use case: {USE_CASE_NAME}")
    print("=" * 80)

    rules = build_shared_rules()
    engine = PhreakEngine()
    engine.load_rules(rules)

    print(f"Loaded {len(rules)} rules. Evaluating facts...\n")

    for fact in SHARED_FACTS:
        result = engine.evaluate(fact)
        print(
            f"fact={fact['fact_id']} "
            f"matched={result.fired_rules} "
            f"actions={result.actions}"
        )

    print(
        f"\nEvaluated {len(SHARED_FACTS)} facts. Working memory independent per eval."
    )


if __name__ == "__main__":
    main()
