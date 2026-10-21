"""Batch 1 example: operator mix in one complex payment-risk use case.

Rewrites the same rule as examples/01_conditions_dict.py but authors it with
the F DSL - compare the two files to see why the fluent form is easier to read
and maintain.

Operator precedence reminder
-----------------------------
Python's ``&`` and ``|`` bind more tightly than ``>``, ``<``, ``==``.
Always parenthesise each individual condition::

    (F("amount") > 2000) & (F("country") == "NG")   # correct
    F("amount") > 2000 & F("country") == "NG"        # wrong - TypeError
"""

from shared_use_case import SHARED_FACTS, USE_CASE_NAME

from fluxrules import F, Rule
from fluxrules.engine.phreak import PhreakEngine


def build_operator_rich_rule() -> Rule:
    return Rule(
        id=101,
        name="operator_rich_triage",
        conditions=(
            (F("amount") > 2000)
            & (F("chargeback_ratio") >= 0.1)
            & (F("payment_method").isin(["crypto", "prepaid_card"]))
            & (F("tags").contains("manual_review_candidate"))
            & (
                (F("country").isin(["NG", "SN", "GH"]))
                | (F("ip_risk_score") >= 70)
            )
            & (
                (F("device_age_days") < 7)
                | (F("account_age_days") < 14)
            )
            & ~(F("email_domain").ends_with("trusted.example"))
        ),
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
