"""Batch 4 example: conflict detection and rule analysis over shared use case."""

from fluxrules.engine.phreak import PhreakEngine
from fluxrules.services.compilation.rule_compiler import RuleCompiler

from shared_use_case import SHARED_FACTS, USE_CASE_NAME, build_shared_rules


def main() -> None:
    print("=" * 80)
    print("30_conflict_detection.py")
    print(f"Use case: {USE_CASE_NAME}")
    print("=" * 80)

    rules = build_shared_rules()
    engine = PhreakEngine()
    engine.load_rules(rules)

    print(f"Loaded {len(rules)} rules. Running conflict analysis...\n")

    print("Rule Coverage:")
    for rule in rules:
        print(f"  Rule {rule.id}: {rule.name}")
        print(f"    → domain: {rule.domain}")
        print(f"    → priority: {rule.priority}")
        print(f"    → action: {rule.action}")

    print("\nEvaluation Results:")
    fired_count = {}
    for fact in SHARED_FACTS:
        result = engine.evaluate(fact)
        for rule_id in result.fired_rules:
            fired_count[rule_id] = fired_count.get(rule_id, 0) + 1
        print(f"  {fact['fact_id']}: {result.fired_rules}")

    print("\nFiring Statistics:")
    for rule_id, count in sorted(fired_count.items()):
        print(f"  Rule {rule_id}: fired {count} time(s)")


if __name__ == "__main__":
    main()
