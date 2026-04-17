"""Tests for incremental RETE assert/retract behavior."""

from app.engine.rete_network import ReteNetwork


def test_assert_and_retract_fact_stateful_path():
    network = ReteNetwork()
    rules = [
        {
            "id": 10,
            "name": "US High Value",
            "priority": 100,
            "action": "alert",
            "condition_dsl": {
                "type": "group",
                "op": "AND",
                "children": [
                    {"type": "condition", "field": "amount", "op": ">", "value": 100},
                    {"type": "condition", "field": "country", "op": "==", "value": "US"},
                ],
            },
        }
    ]

    assert network.compile(rules) is True

    event_one = {"amount": 250, "country": "US"}
    event_two = {"amount": 75, "country": "US"}
    event_three = {"amount": 300, "country": "US"}

    matched_one = network.assert_fact("fact-1", event_one)
    matched_two = network.assert_fact("fact-2", event_two)
    matched_three = network.assert_fact("fact-3", event_three)

    assert [t.rule_id for t in matched_one] == [10]
    assert matched_two == []
    assert [t.rule_id for t in matched_three] == [10]

    fact_one_hash = hash(network._make_hashable(event_one))
    fact_two_hash = hash(network._make_hashable(event_two))
    fact_three_hash = hash(network._make_hashable(event_three))

    # Alpha memory path validation
    for alpha in network._alpha_nodes.values():
        condition_field = alpha.condition.field
        if condition_field == "amount":
            assert fact_one_hash in alpha.alpha_memory
            assert fact_two_hash not in alpha.alpha_memory
            assert fact_three_hash in alpha.alpha_memory

    # Beta memory path validation (only matched facts appear)
    stateful_betas = [b for b in network._beta_nodes if b.tuple_memory]
    assert stateful_betas, "Expected stateful beta memory after assertions"
    all_beta_hashes = {tpl[0] for beta in stateful_betas for tpl in beta.tuple_memory}
    assert fact_one_hash in all_beta_hashes
    assert fact_two_hash not in all_beta_hashes
    assert fact_three_hash in all_beta_hashes

    cancelled = network.retract_fact("fact-3", event_three)

    # Retract path validation
    assert [t.rule_id for t in cancelled] == [10]
    for alpha in network._alpha_nodes.values():
        assert fact_three_hash not in alpha.alpha_memory

    all_beta_hashes_after = {tpl[0] for beta in network._beta_nodes for tpl in beta.tuple_memory}
    assert fact_three_hash not in all_beta_hashes_after
