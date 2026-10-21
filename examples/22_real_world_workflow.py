"""Batch 3 example: an end-to-end payment triage workflow.

The pieces from earlier examples, put together the way a service would use them:

1. **Validate** the ruleset once at startup, and refuse to start if it is broken.
2. **Normalize** each incoming payment with a ``FactPipeline``.
3. **Evaluate** the fact with ``evaluate()``.
4. **Act** on the fired actions through the action registry, or approve.
5. **Explain** a decision later from its ``execution_id``, for audit or support.
"""

from __future__ import annotations

from shared_use_case import SHARED_FACTS, USE_CASE_NAME, build_shared_rules

from fluxrules import evaluate, explain, validate
from fluxrules.pipeline import FactPipeline, FieldType, Require
from fluxrules.plugins.actions import action, action_registry


@action(name="block_payment", category="payments")
def block_payment(**_: object) -> str:
    return "blocked"


@action(name="manual_review", category="operations")
def manual_review(**_: object) -> str:
    return "queued for review"


@action(name="step_up_auth", category="identity")
def step_up_auth(**_: object) -> str:
    return "challenged with step-up auth"


NORMALIZE = FactPipeline(
    [
        Require(["fact_id", "amount", "country"]),
        FieldType({"amount": float, "ip_risk_score": int}),
    ],
    name="normalize_payment",
)


def main() -> None:
    print("=" * 80)
    print("22_real_world_workflow.py")
    print(f"Use case: {USE_CASE_NAME}")
    print("=" * 80)

    rules = build_shared_rules()

    print("\nStep 1: validate the ruleset at startup")
    issues = validate(rules)
    if issues:
        raise SystemExit(f"refusing to start, invalid rules: {issues}")
    print(f"  {len(rules)} rules valid")

    print("\nSteps 2 to 4: normalize, evaluate, act")
    decisions: dict[str, str] = {}
    for raw in SHARED_FACTS:
        fact = NORMALIZE(raw)
        result = evaluate(rules, fact)
        decisions[fact["fact_id"]] = result.execution_id
        if not result.actions:
            print(f"  {fact['fact_id']}: approved")
            continue
        # The highest-priority action decides the outcome; the rest still run.
        for name in result.actions:
            outcome = action_registry.execute(name, **fact)["result"]
            print(f"  {fact['fact_id']}: {outcome}")

    print("\nStep 5: explain a past decision")
    record = explain(decisions["txn-002"])
    print(f"  execution {record['execution_id']}")
    print(f"  fired rules: {record['fired_rules']}")
    print(f"  actions:     {record['actions']}")


if __name__ == "__main__":
    main()
