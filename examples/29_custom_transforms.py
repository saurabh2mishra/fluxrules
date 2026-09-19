"""Batch 4 example: custom fact transformations over shared use case."""

from fluxrules.engine.phreak import PhreakEngine

from shared_use_case import SHARED_FACTS, USE_CASE_NAME, build_shared_rules


def main() -> None:
    print("=" * 80)
    print("29_custom_transforms.py")
    print(f"Use case: {USE_CASE_NAME}")
    print("=" * 80)

    rules = build_shared_rules()
    engine = PhreakEngine()
    engine.load_rules(rules)

    print(f"Loaded {len(rules)} rules. Applying custom transforms...\n")

    def enrich_fact(fact: dict) -> dict:
        """Add computed fields to fact."""
        enriched = fact.copy()
        enriched["risk_score"] = (
            fact.get("amount", 0) / 5000.0 +
            fact.get("velocity_1h", 0) / 10.0 +
            fact.get("ip_risk_score", 0) / 100.0
        ) / 3.0
        return enriched

    for fact in SHARED_FACTS:
        enriched = enrich_fact(fact)
        result = engine.evaluate(enriched)
        print(f"fact={fact['fact_id']} risk_score={enriched['risk_score']:.2f} matched={result.fired_rules}")


if __name__ == "__main__":
    main()
