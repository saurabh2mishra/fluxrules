"""Batch 4 example: nested fact structures over shared use case."""

from fluxrules.engine.phreak import PhreakEngine

from shared_use_case import SHARED_FACTS, USE_CASE_NAME, build_shared_rules


def main() -> None:
    print("=" * 80)
    print("25_nested_facts.py")
    print(f"Use case: {USE_CASE_NAME}")
    print("=" * 80)

    rules = build_shared_rules()
    engine = PhreakEngine()
    engine.load_rules(rules)

    print(f"Loaded {len(rules)} rules. Processing nested fact structures...\n")

    for fact in SHARED_FACTS:
        result = engine.evaluate(fact)
        print(f"Fact: {fact['fact_id']}")
        print(f"  → matched: {result.fired_rules}")
        print(f"  → actions: {result.actions}")


if __name__ == "__main__":
    main()
