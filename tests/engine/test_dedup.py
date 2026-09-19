"""Tests for the fact deduplication framework.

Core guarantee (plan §4.1, ``test_dedup`` gate): a cached result equals a fresh
``evaluate`` for the same fact. Deduplication only avoids recomputation; it never
changes the answer.
"""

from __future__ import annotations

import random

import pytest

from fluxrules import Rule
from fluxrules.engine.phreak import PhreakEngine
from fluxrules.engine.runtime import (
    DedupEvaluator,
    LRUDedupBackend,
    canonical_fact_key,
)


def _leaf(rid: int, field: str, op: str, value) -> Rule:
    return Rule(
        id=rid,
        name=f"rule_{rid}",
        condition_dsl={"type": "condition", "field": field, "op": op, "value": value},
        priority=rid % 5,
        domain=f"d{rid % 3}",
        tags=frozenset(),
        persist=False,
    )


def _engine(rules) -> PhreakEngine:
    eng = PhreakEngine(streaming_mode=False)
    eng.load_rules(rules)
    return eng


# canonical key


def test_canonical_key_is_order_independent():
    assert canonical_fact_key({"a": 1, "b": 2}) == canonical_fact_key({"b": 2, "a": 1})


def test_canonical_key_distinguishes_values():
    assert canonical_fact_key({"a": 1}) != canonical_fact_key({"a": 2})


def test_canonical_key_handles_unserializable_values():
    # Must not raise on exotic value types.
    key = canonical_fact_key({"a": {1, 2, 3}})
    assert isinstance(key, str)


# LRU backend


def test_lru_evicts_least_recently_used():
    backend = LRUDedupBackend(max_entries=2)
    from fluxrules.engine.infrastructure.evaluation_result import EvaluationResult

    backend.put("a", EvaluationResult(fired_rules=[1]))
    backend.put("b", EvaluationResult(fired_rules=[2]))
    backend.get("a")  # touch a -> b is now LRU
    backend.put("c", EvaluationResult(fired_rules=[3]))  # evicts b
    assert backend.get("b") is None
    assert backend.get("a") is not None
    assert backend.get("c") is not None
    assert len(backend) == 2


def test_lru_rejects_nonpositive_size():
    with pytest.raises(ValueError):
        LRUDedupBackend(max_entries=0)


# dedup parity gate


def test_cached_result_equals_fresh_evaluate():
    rules = [_leaf(i, f"field_{i % 4}", ">", i * 10) for i in range(20)]
    fresh = _engine(rules)
    dedup = DedupEvaluator(_engine(rules))

    rng = random.Random(42)
    for _ in range(200):
        fact = {f"field_{j}": rng.randint(0, 200) for j in range(4)}
        expected = set(fresh.evaluate(fact).fired_rules)
        got = set(dedup.evaluate(fact).fired_rules)
        assert got == expected


def test_repeated_fact_hits_cache_without_reevaluating():
    rules = [_leaf(1, "x", ">", 5)]
    engine = _engine(rules)

    calls = {"n": 0}
    original = engine.evaluate

    def counting_evaluate(facts, **kwargs):
        calls["n"] += 1
        return original(facts, **kwargs)

    engine.evaluate = counting_evaluate  # type: ignore[method-assign]
    dedup = DedupEvaluator(engine)

    fact = {"x": 10}
    r1 = dedup.evaluate(fact)
    r2 = dedup.evaluate(fact)
    r3 = dedup.evaluate(fact)

    assert calls["n"] == 1  # only the first computed
    assert dedup.stats.hits == 2
    assert dedup.stats.misses == 1
    assert dedup.stats.hit_rate == pytest.approx(2 / 3)
    assert set(r1.fired_rules) == set(r2.fired_rules) == set(r3.fired_rules)


def test_distinct_facts_each_miss():
    rules = [_leaf(1, "x", ">", 5)]
    dedup = DedupEvaluator(_engine(rules))
    for i in range(10):
        dedup.evaluate({"x": i})
    assert dedup.stats.misses == 10
    assert dedup.stats.hits == 0


def test_clear_resets_cache_and_stats():
    rules = [_leaf(1, "x", ">", 5)]
    dedup = DedupEvaluator(_engine(rules))
    dedup.evaluate({"x": 10})
    dedup.evaluate({"x": 10})
    dedup.clear()
    assert dedup.stats.total == 0
    assert len(dedup.backend) == 0


def test_streaming_engine_is_rejected():
    engine = PhreakEngine(streaming_mode=True)
    engine.load_rules([_leaf(1, "x", ">", 5)])
    with pytest.raises(ValueError):
        DedupEvaluator(engine)
