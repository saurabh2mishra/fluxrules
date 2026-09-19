"""Batch 2 example: REST API-like workflow over shared use case."""

import json

from shared_use_case import SHARED_FACTS, USE_CASE_NAME, build_shared_rules

from fluxrules.engine.phreak import PhreakEngine


def main() -> None:
    print("=" * 80)
    print("12_api_usage.py")
    print(f"Use case: {USE_CASE_NAME}")
    print("=" * 80)

    rules = build_shared_rules()
    engine = PhreakEngine()
    engine.load_rules(rules)

    print(f"Loaded {len(rules)} rules. Simulating REST API requests...\n")

    for fact in SHARED_FACTS:
        result = engine.evaluate(fact)
        response = {
            "fact_id": fact["fact_id"],
            "matched_rules": result.fired_rules,
            "actions": result.actions,
            "latency_ms": result.latency_ms,
        }

        print(f"POST /evaluate")
        print(f"Response: {json.dumps(response)}\n")


if __name__ == "__main__":
    main()
