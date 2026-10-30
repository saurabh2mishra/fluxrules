"""Shared payment risk dataset and complex rules for examples.

All examples in the docs rewrite program should import from this module so the
same underlying data model is used consistently.
"""

from __future__ import annotations

from fluxrules import F, Rule
from fluxrules.domain.field import Condition

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


def complex_risk_condition() -> Condition:
    """Return the canonical nested condition with eight checks, written with F.

    Read top to bottom: a large, fast, charged-back payment, from a risky
    country or IP, on a new device or account, not from a trusted email domain,
    using a risky payment method and flagged for manual review.
    """
    return (
        (F("amount") > 2000)
        & (F("velocity_1h") >= 3)
        & (F("chargeback_ratio") > 0.08)
        & ((F("country").isin(["NG", "SN", "GH"])) | (F("ip_risk_score") >= 70))
        & ((F("device_age_days") < 7) | (F("account_age_days") < 14))
        & ~(F("email_domain").ends_with("trusted.example"))
        & (F("payment_method").isin(["crypto", "prepaid_card"]))
        & (F("tags").contains("manual_review_candidate"))
    )


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
            conditions=base,
            action="manual_review",
            priority=20,
        ),
        Rule(
            id=1002,
            name="triage_for_hard_block",
            domain="compliance",
            tags=frozenset(["tier_2", "block", "geo_risk"]),
            conditions=base & (F("ip_risk_score") >= 85),
            action="block_payment",
            priority=30,
        ),
        Rule(
            id=1003,
            name="triage_for_step_up_auth",
            domain="risk_ops",
            tags=frozenset(["tier_1", "step_up", "identity"]),
            conditions=base & ((F("customer_tier") == "standard") | (F("currency") == "USD")),
            action="step_up_auth",
            priority=15,
        ),
    ]
