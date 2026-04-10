"""Scenario test for RETE behavior with multi-fact loan-approval rules."""

from __future__ import annotations

from app.engine.rete_network import ReteEngine


def _flatten_facts(facts: dict) -> dict:
    return {
        f"{fact}.{field}": value
        for fact, payload in facts.items()
        for field, value in payload.items()
    }


def _to_fluxrules_rules(rule_db: list[dict]) -> list[dict]:
    rules = []
    for i, rule in enumerate(rule_db, start=1):
        children = [
            {
                "type": "condition",
                "field": f"{c['fact']}.{c['field']}",
                "op": c["operator"],
                "value": c["value"],
            }
            for c in rule["conditions"]
        ]
        rules.append(
            {
                "id": i,
                "name": rule["rule_name"],
                "priority": 100 - i,
                "action": rule["action"],
                "condition_dsl": {
                    "type": "group",
                    "op": "AND",
                    "children": children,
                },
            }
        )
    return rules


def _scenario_payloads() -> tuple[dict, list[dict]]:
    facts = {
        "Applicant": {
            "age": 32,
            "credit_score": 720,
            "income": 65000,
            "employment_years": 5,
            "country": "NL",
        },
        "Loan": {
            "amount": 15000,
            "type": "personal",
            "tenure_months": 36,
        },
        "Account": {
            "existing_loans": 1,
            "missed_payments": 0,
        },
    }

    rule_db = [
        {
            "rule_name": "Approve Good Credit",
            "conditions": [
                {"fact": "Applicant", "field": "credit_score", "operator": ">=", "value": 700},
                {"fact": "Loan", "field": "amount", "operator": "<=", "value": 20000},
            ],
            "action": "approveLoan",
        },
        {
            "rule_name": "Employment Stability Discount",
            "conditions": [
                {"fact": "Applicant", "field": "employment_years", "operator": ">=", "value": 3}
            ],
            "action": "applyInterestDiscount",
        },
        {
            "rule_name": "Low Risk Flag",
            "conditions": [
                {"fact": "Account", "field": "missed_payments", "operator": "==", "value": 0},
                {"fact": "Applicant", "field": "credit_score", "operator": ">", "value": 680},
            ],
            "action": "setRiskLow",
        },
        {
            "rule_name": "Fast Track Small Loan",
            "conditions": [
                {"fact": "Loan", "field": "amount", "operator": "<", "value": 20000},
                {"fact": "Loan", "field": "tenure_months", "operator": "<=", "value": 36},
            ],
            "action": "enableFastTrack",
        },
        {
            "rule_name": "Netherlands Resident Cashback",
            "conditions": [
                {"fact": "Applicant", "field": "country", "operator": "==", "value": "NL"}
            ],
            "action": "applyCashback",
        },
        {
            "rule_name": "Reject Low Credit",
            "conditions": [
                {"fact": "Applicant", "field": "credit_score", "operator": "<", "value": 600}
            ],
            "action": "rejectLoan",
        },
        {
            "rule_name": "Reject Overleveraged",
            "conditions": [
                {"fact": "Account", "field": "existing_loans", "operator": ">=", "value": 3},
                {"fact": "Loan", "field": "amount", "operator": ">", "value": 10000},
            ],
            "action": "rejectLoan",
        },
    ]
    return facts, rule_db


def test_rete_behavior_for_credit_loan_scenario():
    facts, rule_db = _scenario_payloads()
    event = _flatten_facts(facts)
    rules = _to_fluxrules_rules(rule_db)

    engine = ReteEngine(db=None)
    assert engine.load_rules(rules) is True

    result = engine.evaluate(event)
    fired_rules = [r["name"] for r in result["matched_rules"]]
    expected_fired = [
        "Approve Good Credit",
        "Employment Stability Discount",
        "Low Risk Flag",
        "Fast Track Small Loan",
        "Netherlands Resident Cashback",
    ]

    assert len(fired_rules) == 5
    assert fired_rules == expected_fired
    assert "Reject Low Credit" not in fired_rules
    assert "Reject Overleveraged" not in fired_rules
    assert "Approve Good Credit" in fired_rules
    assert "Low Risk Flag" in fired_rules

    # Idempotency: same inputs should produce same activations.
    result_2 = engine.evaluate(event)
    fired_rules_2 = [r["name"] for r in result_2["matched_rules"]]
    assert fired_rules_2 == fired_rules

    # Rete optimization stats should be populated.
    stats = result["stats"]
    assert stats["optimization"] == "rete"
    assert stats["alpha_nodes"] > 0
    assert stats["beta_nodes"] > 0

