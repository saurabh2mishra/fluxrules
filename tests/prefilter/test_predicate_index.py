"""Soundness tests for the in-memory streaming PredicateIndex.

The single most important property: the pre-screen must never drop a fact that a
rule could fire on (no false negatives). False positives are fine - the engine
removes them. These tests fuzz random rules + facts and assert the screen is a
superset of the true firing set, plus check that it actually reduces work and
degrades safely to pass-through on unsupported constructs.
"""

from __future__ import annotations

import random
from types import SimpleNamespace

import pytest

from fluxrules.prefilter import PredicateExtractor, PredicateIndex

# minimal engine-equivalent oracle
# Mirrors the operator semantics the extractor relies on (absent field -> False).


def _eval_leaf(fact: dict, dsl: dict) -> bool:
    f, op, val = dsl["field"], dsl["op"], dsl.get("value")
    if f not in fact:
        return False
    v = fact[f]
    if v is None:
        return op == "==" and val is None
    if op == ">":
        return v > val
    if op == ">=":
        return v >= val
    if op == "<":
        return v < val
    if op == "<=":
        return v <= val
    if op == "==":
        return v == val
    if op == "!=":
        return v != val
    if op == "in":
        return v in val
    raise ValueError(op)


def _eval(fact: dict, dsl: dict) -> bool:
    t = dsl["type"]
    if t == "condition":
        return _eval_leaf(fact, dsl)
    if t == "and":
        return all(_eval(fact, c) for c in dsl["conditions"])
    if t == "or":
        return any(_eval(fact, c) for c in dsl["conditions"])
    if t == "not":
        return not _eval(fact, dsl["condition"])
    raise ValueError(t)


def _rule(rid: int, dsl: dict) -> SimpleNamespace:
    return SimpleNamespace(id=rid, enabled=True, conditions=dsl)


# generators

_FIELDS = [f"field_{i}" for i in range(8)]
_RANGE_OPS = [">", ">=", "<", "<="]


def _rand_leaf(rng: random.Random) -> dict:
    f = rng.choice(_FIELDS)
    op = rng.choice(_RANGE_OPS + ["=="])
    val = rng.randint(0, 100)
    return {"type": "condition", "field": f, "op": op, "value": val}


def _rand_rule(rng: random.Random, rid: int) -> SimpleNamespace:
    kind = rng.choice(["leaf", "and", "or"])
    if kind == "leaf":
        return _rule(rid, _rand_leaf(rng))
    n = rng.randint(2, 3)
    return _rule(rid, {"type": kind, "conditions": [_rand_leaf(rng) for _ in range(n)]})


def _rand_fact(rng: random.Random) -> dict:
    # Sparse facts: some fields absent, to exercise NULL handling.
    return {f: rng.randint(0, 100) for f in _FIELDS if rng.random() < 0.7}


@pytest.mark.parametrize("seed", [1, 7, 42, 100, 2024])
def test_predicate_index_is_sound(seed: int) -> None:
    rng = random.Random(seed)
    rules = [_rand_rule(rng, i) for i in range(50)]
    facts = [_rand_fact(rng) for _ in range(5000)]

    index = PredicateIndex.from_rules(rules)

    for fact in facts:
        fires = any(_eval(fact, r.conditions) for r in rules)
        if fires:
            # Hard gate: every firing fact MUST be a candidate.
            assert index.matches(fact), f"false negative on {fact}"


def test_predicate_index_reduces_work() -> None:
    rng = random.Random(0)
    # Selective rules -> most random facts should be screened out.
    rules = [
        _rule(i, {"type": "condition", "field": f"field_{i % 4}", "op": ">", "value": 95})
        for i in range(20)
    ]
    facts = [_rand_fact(rng) for _ in range(5000)]
    index = PredicateIndex.from_rules(rules)
    candidates = list(index.filter(facts))
    assert len(candidates) < len(facts)  # actually filters
    # And remains sound.
    for fact in facts:
        if any(_eval(fact, r.conditions) for r in rules):
            assert fact in candidates


def test_unsupported_construct_degrades_to_pass_through() -> None:
    rules = [
        _rule(
            1,
            {
                "type": "not",
                "condition": {
                    "type": "condition",
                    "field": "x",
                    "op": "==",
                    "value": 1,
                },
            },
        ),
    ]
    index = PredicateIndex.from_rules(rules)
    assert index.pass_through is True
    assert index.matches({}) is True  # nothing is ever dropped


def test_shared_predicate_is_interned_once() -> None:
    shared = {"type": "condition", "field": "field_1", "op": ">", "value": 10}
    rules = [_rule(1, dict(shared)), _rule(2, dict(shared)), _rule(3, dict(shared))]
    index = PredicateIndex.from_rules(rules, PredicateExtractor())
    # Three rules sharing one predicate -> one distinct alpha node AND one
    # distinct signature mapped to all three rule ids.
    assert len(index._nodes) == 1
    assert len(index._signatures) == 1
    assert index._signature_rules[0] == frozenset({1, 2, 3})


def test_prune_drops_rules_whose_signature_fails() -> None:
    rules = [
        _rule(1, {"type": "condition", "field": "field_1", "op": ">", "value": 10}),
        _rule(2, {"type": "condition", "field": "field_2", "op": "<", "value": 5}),
        _rule(3, {"type": "condition", "field": "field_1", "op": ">", "value": 10}),
    ]
    index = PredicateIndex.from_rules(rules)
    universe = [3, 2, 1]
    fact = {"field_1": 20, "field_2": 50}

    pruned = index.prune(fact, universe)
    assert pruned == [3, 1]  # rule 2 dropped, caller's order preserved
    assert pruned is not universe
    assert index.candidate_rule_ids(fact, universe) == {1, 3}


@pytest.mark.parametrize("op", [">", ">=", "<", "<="])
def test_ordering_tests_use_the_engine_comparisons(op: str) -> None:
    from fluxrules.engine.operators import COMPARISONS
    from fluxrules.prefilter.predicate_index import _make_test

    test = _make_test(op, 5)
    for v in (4, 5, 6):
        assert test(v) is COMPARISONS[op](v, 5)


def test_an_operator_the_index_does_not_know_keeps_the_rule() -> None:
    # The extractor only emits operators the index can test. Anything else
    # must keep the rule as a candidate, never drop it.
    from fluxrules.prefilter.predicate_index import _MISSING, _make_test

    test = _make_test("contains", "x")
    assert all(test(v) for v in ("abc", 5, None, _MISSING))
