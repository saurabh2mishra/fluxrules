from app.engine.rete_network import BetaNode


def test_stateful_tuple_insertion_and_count():
    beta = BetaNode(stateful=True)

    assert beta.add_tuple("order-1", frozenset({"f1", "f2"})) is True
    assert beta.add_tuple("order-1", frozenset({"f1", "f2"})) is False
    assert beta.add_tuple("order-1", frozenset({"f1", "f3"})) is True
    assert beta.add_tuple("order-2", frozenset({"f10"})) is True
    assert beta.tuple_count() == 3


def test_stateful_retraction_and_clear_memory():
    beta = BetaNode(stateful=True)
    beta.add_tuple("k1", frozenset({"f1", "f2"}))
    beta.add_tuple("k1", frozenset({"f3"}))
    beta.add_tuple("k2", frozenset({"f2", "f4"}))

    removed = beta.remove_tuples_containing("f2")
    assert removed == 2
    assert beta.tuple_count() == 1
    assert "k2" not in beta.tuple_memory

    beta.clear_memory()
    assert beta.tuple_memory == {}
    assert beta.tuple_count() == 0


def test_stateless_parity_and_noop_tuple_methods():
    beta = BetaNode()

    assert beta.stateful is False
    assert beta.add_tuple("k1", frozenset({"f1"})) is False
    assert beta.remove_tuples_containing("f1") == 0
    assert beta.tuple_count() == 0

    beta.beta_memory = True
    beta.clear_memory()
    assert beta.beta_memory is False

    result = beta.evaluate(event={}, event_hash=1, alpha_results={})
    assert result is True
    assert beta.beta_memory is True
