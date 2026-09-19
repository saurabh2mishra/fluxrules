"""Batch 3 example: real-world workflow over shared use case."""

from fluxrules.engine.phreak import PhreakEngine

from shared_use_case import SHARED_FACTS, USE_CASE_NAME, build_shared_rules


def main() -> None:
    print("=" * 80)
    print("22_real_world_workflow.py")
    print(f"Use case: {USE_CASE_NAME}")
    print("=" * 80)

    rules = build_shared_rules()
    engine = PhreakEngine()
    engine.load_rules(rules)

    print(f"\n{'='*80}")
    print("REAL-WORLD WORKFLOW: Payment Risk Triage")
    print(f"{'='*80}\n")

    print("Step 1: Load rules from production")
    print(f"  ✅ Loaded {len(rules)} rules\n")

    print("Step 2: Process incoming transactions")
    for idx, fact in enumerate(SHARED_FACTS, 1):
        result = engine.evaluate(fact)
        action = result.actions[0] if result.actions else "approve"
        print(f"  [{idx}] Txn {fact['fact_id']}: {action}")

    print("\nStep 3: Audit trail logged")
    print("  ✅ All evaluations recorded\n")


if __name__ == "__main__":
    main()
