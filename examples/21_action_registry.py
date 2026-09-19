"""Batch 3 example: action registry patterns over shared use case."""

from fluxrules.engine.phreak import PhreakEngine

from shared_use_case import SHARED_FACTS, USE_CASE_NAME, build_shared_rules


def main() -> None:
    print("=" * 80)
    print("21_action_registry.py")
    print(f"Use case: {USE_CASE_NAME}")
    print("=" * 80)

    rules = build_shared_rules()

    # Extract unique actions from rules
    unique_actions = set()
    for rule in rules:
        unique_actions.add(rule.action)

    print(f"Loaded {len(rules)} rules with {len(unique_actions)} unique actions.")
    print(f"Registry: {unique_actions}\n")

    engine = PhreakEngine()
    engine.load_rules(rules)

    action_counts = {}
    for fact in SHARED_FACTS:
        result = engine.evaluate(fact)
        for action in result.actions:
            action_counts[action] = action_counts.get(action, 0) + 1

    print("Action execution counts:")
    for action, count in sorted(action_counts.items()):
        print(f"  {action}: {count}")


if __name__ == "__main__":
    main()
