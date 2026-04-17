"""Integration coverage for evaluator-backed and stateful RETE beta nodes."""

from app.engine.rete_network import ReteNetwork


def test_accumulate_condition_matches_with_evaluator_backed_beta():
    network = ReteNetwork()
    rules = [
        {
            "id": 1,
            "name": "High Spenders",
            "priority": 10,
            "action": "flag",
            "condition_dsl": {
                "type": "accumulate",
                "source": "transactions",
                "field": "amount",
                "aggregate": "sum",
                "op": ">=",
                "value": 150,
            },
        }
    ]

    assert network.compile(rules) is True

    low_total = network.evaluate(
        {
            "transactions": [
                {"amount": 50},
                {"amount": 75},
            ]
        }
    )
    assert len(low_total) == 0

    high_total = network.evaluate(
        {
            "transactions": [
                {"amount": 80},
                {"amount": 75},
            ]
        }
    )
    assert len(high_total) == 1
    assert high_total[0].rule_name == "High Spenders"


def test_sequence_condition_matches_ordered_steps_with_evaluator_backed_beta():
    network = ReteNetwork()
    rules = [
        {
            "id": 2,
            "name": "Lifecycle Sequence",
            "priority": 10,
            "action": "mark_complete",
            "condition_dsl": {
                "type": "sequence",
                "source": "events",
                "steps": [
                    {"type": "condition", "field": "status", "op": "==", "value": "created"},
                    {"type": "condition", "field": "status", "op": "==", "value": "approved"},
                    {"type": "condition", "field": "status", "op": "==", "value": "settled"},
                ],
            },
        }
    ]

    assert network.compile(rules) is True

    ordered_match = network.evaluate(
        {
            "events": [
                {"status": "created"},
                {"status": "approved"},
                {"status": "settled"},
            ]
        }
    )
    assert len(ordered_match) == 1

    out_of_order = network.evaluate(
        {
            "events": [
                {"status": "approved"},
                {"status": "created"},
                {"status": "settled"},
            ]
        }
    )
    assert len(out_of_order) == 0


def test_cross_fact_join_is_stateful_and_skipped_in_stateless_evaluate():
    network = ReteNetwork()
    rules = [
        {
            "id": 3,
            "name": "Cross Fact Correlation",
            "priority": 1,
            "action": "correlate",
            "condition_dsl": {
                "type": "cross_fact_join",
                "correlate_field": "account_id",
            },
        }
    ]

    assert network.compile(rules) is True

    # Stateless evaluate() must skip stateful-only node types.
    skipped_match = network.evaluate({"account_id": "A-100", "kind": "invoice"})
    assert skipped_match == []

    cross_beta = next(beta for beta in network._beta_nodes if beta.node_type == "cross_fact_join")
    assert cross_beta.stateful is True

    # Stateful evaluator tracks tuples by correlate field.
    first = cross_beta.evaluate(
        {"account_id": "A-100", "kind": "invoice"},
        101,
        {},
        stateless_mode=False,
    )
    second = cross_beta.evaluate(
        {"account_id": "A-100", "kind": "payment"},
        102,
        {},
        stateless_mode=False,
    )

    assert first is False
    assert second is True
    assert len(cross_beta.tuple_memory["A-100"]) == 2
