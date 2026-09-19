"""Batch 1 example: domains and tags for one complex payment-risk use case."""

from shared_use_case import SHARED_FACTS, USE_CASE_NAME, build_shared_rules

from fluxrules.engine.phreak import PhreakEngine


def evaluate_subset(label: str, rules) -> None:
    engine = PhreakEngine()
    engine.load_rules(rules)
    print(label)
    for fact in SHARED_FACTS:
        result = engine.evaluate(fact)
        print(
            f"  fact={fact['fact_id']} matched={result.fired_rules} actions={result.actions}"
        )


def main() -> None:
    print("=" * 80)
    print("03_domains_and_tags.py")
    print(f"Use case: {USE_CASE_NAME}")
    print("=" * 80)

    rules = build_shared_rules()
    evaluate_subset("all domains", rules)

    fraud_rules = [rule for rule in rules if rule.domain == "fraud_detection"]
    evaluate_subset("fraud_detection domain", fraud_rules)

    tier1_rules = [rule for rule in rules if "tier_1" in rule.tags]
    evaluate_subset("tier_1 tag", tier1_rules)


if __name__ == "__main__":
    main()
