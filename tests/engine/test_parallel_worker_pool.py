"""Tests for the process-based parallel evaluation helper.

Core guarantee: parallel batch evaluation must produce *exactly* the same
fired-rule sets as single-process stateless evaluation. Only the distribution
of work changes, never the result.
"""

from __future__ import annotations

import random

import pytest

from fluxrules import Rule
from fluxrules.engine.phreak import PhreakEngine
from fluxrules.engine.runtime import evaluate_batch_parallel


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


def _single_process_results(rules, facts) -> list[set[int]]:
    engine = PhreakEngine(streaming_mode=False)
    engine.load_rules(rules)
    return [set(engine.evaluate(f).fired_rules) for f in facts]


def test_empty_facts_returns_empty():
    assert evaluate_batch_parallel(rules=[], facts=[], num_workers=2) == []


def test_single_worker_matches_single_process():
    rules = [_leaf(i, f"f{i % 5}", ">", i % 50) for i in range(1, 60)]
    facts = [{f"f{j}": random.randint(0, 100) for j in range(5)} for _ in range(40)]

    parallel = evaluate_batch_parallel(rules, facts, num_workers=1)
    expected = _single_process_results(rules, facts)

    assert [set(r) for r in parallel] == expected


@pytest.mark.parametrize("num_workers", [2, 4])
def test_multi_worker_matches_single_process(num_workers):
    rng = random.Random(42)
    ops = [">", ">=", "<", "<=", "==", "!="]
    rules = [_leaf(i, f"f{i % 6}", rng.choice(ops), rng.randint(0, 100)) for i in range(1, 121)]
    facts = [
        {f"f{j}": rng.randint(0, 100) for j in range(6) if rng.random() < 0.7} for _ in range(80)
    ]

    parallel = evaluate_batch_parallel(rules, facts, num_workers=num_workers)
    expected = _single_process_results(rules, facts)

    assert len(parallel) == len(facts)
    assert [set(r) for r in parallel] == expected


def test_order_is_preserved():
    """Output[i] must correspond to facts[i] even when sharded."""
    rules = [_leaf(1, "x", "==", v) for v in range(1)]  # rule 1: x == 0
    rules = [_leaf(i, "x", "==", i) for i in range(20)]
    facts = [{"x": i} for i in range(20)]

    parallel = evaluate_batch_parallel(rules, facts, num_workers=4)
    # facts[i] = {"x": i} should fire exactly rule i (x == i).
    for i, fired in enumerate(parallel):
        assert set(fired) == {i}
