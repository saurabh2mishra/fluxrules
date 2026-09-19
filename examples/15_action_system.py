"""Batch 3 example: action registry and execution over shared use case."""

from fluxrules.engine.phreak import PhreakEngine

from shared_use_case import SHARED_FACTS, USE_CASE_NAME, build_shared_rules


def main() -> None:
    print("=" * 80)
    print("15_action_system.py")
    print(f"Use case: {USE_CASE_NAME}")
    print("=" * 80)

    rules = build_shared_rules()
    engine = PhreakEngine()
    engine.load_rules(rules)

    print(f"Loaded {len(rules)} rules. Evaluating actions...\n")

    for fact in SHARED_FACTS:
        result = engine.evaluate(fact)
        if result.actions:
            print(f"fact={fact['fact_id']} actions={result.actions}")
            for action in result.actions:
                print(f"  → Execute: {action}")
        else:
            print(f"fact={fact['fact_id']} (no actions triggered)")


if __name__ == "__main__":
    main()
