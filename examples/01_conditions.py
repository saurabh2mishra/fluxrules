"""Batch 1 example: operator mix in one complex payment-risk use case.

The rule below uses comparison, collection, string, membership, and nested
boolean clauses over the shared dataset.
"""

from shared_use_case import SHARED_FACTS, USE_CASE_NAME

from fluxrules.domain import Rule
from fluxrules.engine.phreak import PhreakEngine


def build_operator_rich_rule() -> Rule:
    return Rule(
        id=101,
        name="operator_rich_triage",
        condition_dsl={
            "type": "group",
            "op": "AND",
            "children": [
                {"type": "condition", "field": "amount", "op": ">", "value": 2000},
                {
                    "type": "condition",
                    "field": "chargeback_ratio",
                    "op": ">=",
                    "value": 0.1,
                },
                {
                    "type": "condition",
                    "field": "payment_method",
                    "op": "in",
                    "value": ["crypto", "prepaid_card"],
                },
                {
                    "type": "condition",
                    "field": "tags",
                    "op": "contains",
                    "value": "manual_review_candidate",
                },
                {
                    "type": "group",
                    "op": "OR",
                    "children": [
                        {
                            "type": "condition",
                            "field": "country",
                            "op": "in",
                            "value": ["NG", "SN", "GH"],
                        },
                        {
                            "type": "condition",
                            "field": "ip_risk_score",
                            "op": ">=",
                            "value": 70,
                        },
                    ],
                },
                {
                    "type": "group",
                    "op": "OR",
                    "children": [
                        {
                            "type": "condition",
                            "field": "device_age_days",
                            "op": "<",
                            "value": 7,
                        },
                        {
                            "type": "condition",
                            "field": "account_age_days",
                            "op": "<",
                            "value": 14,
                        },
                    ],
                },
                {
                    "type": "not",
                    "condition": {
                        "type": "condition",
                        "field": "email_domain",
                        "op": "ends_with",
                        "value": "trusted.example",
                    },
                },
            ],
        },
        action="manual_review",
        priority=25,
        domain="fraud_detection",
    )


def main() -> None:
    print("=" * 80)
    print("01_conditions.py")
    print(f"Use case: {USE_CASE_NAME}")
    print("=" * 80)

    engine = PhreakEngine()
    engine.load_rules([build_operator_rich_rule()])

    for fact in SHARED_FACTS:
        result = engine.evaluate(fact)
        print(
            f"fact={fact['fact_id']} matched={result.fired_rules} actions={result.actions}"
        )


if __name__ == "__main__":
    main()
