"""Batch 4 example: high-priority fact pipeline over shared use case."""

from fluxrules.engine.phreak import PhreakEngine

from shared_use_case import SHARED_FACTS, USE_CASE_NAME, build_shared_rules


def main() -> None:
    print("=" * 80)
    print("28_factpipeline_tier1.py")
    print(f"Use case: {USE_CASE_NAME}")
    print("=" * 80)

    rules = build_shared_rules()
    
    # Filter for tier_0 rules only
    tier0_rules = [r for r in rules if "tier_0" in (r.tags or [])]
    
    engine = PhreakEngine()
    engine.load_rules(tier0_rules)

    print(f"Tier 0 rules: {len(tier0_rules)} / {len(rules)} total\n")

    for fact in SHARED_FACTS:
        result = engine.evaluate(fact)
        print(f"fact={fact['fact_id']} matched={result.fired_rules}")


if __name__ == "__main__":
    main()
