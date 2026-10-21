"""Batch 4 example: cross-fact joins with CrossFactEngine.

``PhreakEngine`` evaluates one fact at a time. When a rule has to relate two
facts, such as a payment and the customer who made it, use ``CrossFactEngine``.
It keeps typed facts in working memory and matches tuples of facts:

- a ``Pattern`` matches one fact type and can carry field-vs-literal constraints;
- a join ties a field to a field of a fact bound by an earlier pattern.

Every ``insert``, ``update`` or ``retract`` returns the activations that were
added or removed, so the engine stays correct as facts come and go.

Rule here: a payment over 2000 from a customer whose account is under 14 days old.
"""

from __future__ import annotations

from shared_use_case import USE_CASE_NAME

from fluxrules.engine.cross_fact import CrossFactEngine, CrossFactRule, Pattern

NEW_ACCOUNT_LARGE_PAYMENT = CrossFactRule(
    id=1,
    name="large_payment_from_new_account",
    action="manual_review",
    patterns=[
        Pattern("p", "Payment", constraints=[("amount", ">", 2000)]),
        Pattern(
            "c",
            "Customer",
            constraints=[("account_age_days", "<", 14)],
            joins=[("id", "==", "p", "customer_id")],
        ),
    ],
)


def show(label: str, delta) -> None:
    added = [f"+{a.rule_name}(p={a.bindings['p']['payment_id']})" for a in delta.added]
    removed = [f"-{a.rule_name}(p={a.bindings['p']['payment_id']})" for a in delta.removed]
    print(f"  {label:48} {' '.join(added + removed) or 'no change'}")


def main() -> None:
    print("=" * 80)
    print("24_cross_fact_joins.py")
    print(f"Use case: {USE_CASE_NAME}")
    print("=" * 80)

    engine = CrossFactEngine()
    engine.load_rules([NEW_ACCOUNT_LARGE_PAYMENT])

    print("\nFacts arrive in any order; the join fires once both sides exist:\n")
    show(
        "insert Payment txn-001 (4200, customer c1)",
        engine.insert("Payment", {"payment_id": "txn-001", "customer_id": "c1", "amount": 4200}),
    )
    customer = engine.insert("Customer", {"id": "c1", "account_age_days": 5})
    show("insert Customer c1 (5 days old)", customer)
    show(
        "insert Payment txn-002 (950, customer c1)",
        engine.insert("Payment", {"payment_id": "txn-002", "customer_id": "c1", "amount": 950}),
    )
    show(
        "insert Payment txn-003 (2600, customer c2)",
        engine.insert("Payment", {"payment_id": "txn-003", "customer_id": "c2", "amount": 2600}),
    )
    show("insert Customer c2 (540 days old)", engine.insert("Customer", {"id": "c2", "account_age_days": 540}))

    print(f"\nActive matches: {[a.bindings['p']['payment_id'] for a in engine.activations()]}")

    print("\nUpdating or retracting a fact removes the matches that depended on it:\n")
    show(
        "update Customer c1 to 30 days old",
        engine.update(customer.handle.id, {"id": "c1", "account_age_days": 30}),
    )
    engine.insert("Customer", {"id": "c3", "account_age_days": 2})
    refunded = engine.insert(
        "Payment", {"payment_id": "txn-004", "customer_id": "c3", "amount": 7000}
    )
    show("insert Payment txn-004 (7000, new customer c3)", refunded)
    show("retract Payment txn-004 (refunded)", engine.retract(refunded.handle.id))
    print(f"\nActive matches: {[a.bindings['p']['payment_id'] for a in engine.activations()]}")


if __name__ == "__main__":
    main()
