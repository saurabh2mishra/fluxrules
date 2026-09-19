"""Batch 2 example: rule persistence and audit trail over shared use case."""

from shared_use_case import SHARED_FACTS, USE_CASE_NAME, build_shared_rules

from fluxrules.engine.phreak import PhreakEngine


def main() -> None:
    print("=" * 80)
    print("05_persistence.py")
    print(f"Use case: {USE_CASE_NAME}")
    print("=" * 80)

    rules = build_shared_rules()
    engine = PhreakEngine()
    engine.load_rules(rules)

    print(f"Loaded {len(rules)} rules. Evaluating facts...\n")

    audit_log = []
    for fact in SHARED_FACTS:
        result = engine.evaluate(fact)
        audit_record = {
            "fact_id": fact["fact_id"],
            "matched_rules": result.fired_rules,
            "actions": result.actions,
            "latency_ms": result.latency_ms,
        }
        audit_log.append(audit_record)
        print(
            f"fact={fact['fact_id']} matched={result.fired_rules} actions={result.actions}"
        )

    print(f"\nPersisted {len(audit_log)} evaluation records to audit trail.")
    print("In production: use database or message queue for durability.")


if __name__ == "__main__":
    main()
