"""Shared payment risk dataset and complex rules for examples.

All examples in the docs rewrite program should import from this module so the
same underlying data model is used consistently.
"""

from __future__ import annotations

from fluxrules.domain import Rule

USE_CASE_NAME = "cross_border_payment_risk_triage"


SHARED_FACTS = [
    {
        "fact_id": "txn-001",
        "amount": 4200,
        "currency": "USD",
        "country": "NG",
        "ip_risk_score": 88,
        "velocity_1h": 6,
        "chargeback_ratio": 0.14,
        "device_age_days": 2,
        "account_age_days": 5,
        "payment_method": "prepaid_card",
        "email_domain": "newmail.example",
        "customer_tier": "standard",
        "tags": ["manual_review_candidate", "cross_border"],
    },
    {
        "fact_id": "txn-002",
        "amount": 2600,
        "currency": "USD",
        "country": "US",
        "ip_risk_score": 74,
        "velocity_1h": 4,
        "chargeback_ratio": 0.11,
        "device_age_days": 12,
        "account_age_days": 9,
        "payment_method": "crypto",
        "email_domain": "buyer.mail",
        "customer_tier": "standard",
        "tags": ["manual_review_candidate"],
    },
    {
        "fact_id": "txn-003",
        "amount": 950,
        "currency": "USD",
        "country": "US",
        "ip_risk_score": 25,
        "velocity_1h": 1,
        "chargeback_ratio": 0.01,
        "device_age_days": 140,
        "account_age_days": 540,
        "payment_method": "card",
        "email_domain": "trusted.example",
        "customer_tier": "vip",
        "tags": ["returning_customer"],
    },
]


def complex_risk_condition() -> dict:
    """Return the canonical nested DSL with at least 7 conditions."""
    return {
        "type": "group",
        "op": "AND",
        "children": [
            {"type": "condition", "field": "amount", "op": ">", "value": 2000},
            {"type": "condition", "field": "velocity_1h", "op": ">=", "value": 3},
            {
                "type": "condition",
                "field": "chargeback_ratio",
                "op": ">",
                "value": 0.08,
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
        ],
    }


def build_shared_rules() -> list[Rule]:
    """Rules over the shared payment-risk use case.

    Every rule keeps at least 7 condition checks and includes nested clauses.
    """
    base = complex_risk_condition()
    return [
        Rule(
            id=1001,
            name="triage_for_manual_review",
            domain="fraud_detection",
            tags=frozenset(["tier_1", "manual_review", "cross_border"]),
            condition_dsl=base,
            action="manual_review",
            priority=20,
        ),
        Rule(
            id=1002,
            name="triage_for_hard_block",
            domain="compliance",
            tags=frozenset(["tier_2", "block", "geo_risk"]),
            condition_dsl={
                "type": "group",
                "op": "AND",
                "children": [
                    *base["children"],
                    {
                        "type": "condition",
                        "field": "ip_risk_score",
                        "op": ">=",
                        "value": 85,
                    },
                ],
            },
            action="block_payment",
            priority=30,
        ),
        Rule(
            id=1003,
            name="triage_for_step_up_auth",
            domain="risk_ops",
            tags=frozenset(["tier_1", "step_up", "identity"]),
            condition_dsl={
                "type": "group",
                "op": "AND",
                "children": [
                    *base["children"],
                    {
                        "type": "group",
                        "op": "OR",
                        "children": [
                            {
                                "type": "condition",
                                "field": "customer_tier",
                                "op": "==",
                                "value": "standard",
                            },
                            {
                                "type": "condition",
                                "field": "currency",
                                "op": "==",
                                "value": "USD",
                            },
                        ],
                    },
                ],
            },
            action="step_up_auth",
            priority=15,
        ),
    ]
