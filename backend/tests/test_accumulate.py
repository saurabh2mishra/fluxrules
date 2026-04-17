from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.engine.accumulate import AccumulateEvaluator
from app.execution.working_memory import WorkingMemory


def _seed_orders(wm: WorkingMemory, now: datetime) -> None:
    a = wm.insert_fact("o-1", {"type": "Order", "account_id": "A", "amount": 10})
    b = wm.insert_fact("o-2", {"type": "Order", "account_id": "A", "amount": 20})
    c = wm.insert_fact("o-3", {"type": "Order", "account_id": "B", "amount": 8})
    d = wm.insert_fact("o-4", {"type": "Order", "account_id": "B", "amount": 12})

    # force deterministic recency for window tests
    a.inserted_at = now - timedelta(seconds=60)
    b.inserted_at = now - timedelta(seconds=30)
    c.inserted_at = now - timedelta(seconds=20)
    d.inserted_at = now - timedelta(seconds=3)


def test_accumulate_count_with_constraint() -> None:
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    wm = WorkingMemory()
    _seed_orders(wm, now)

    evaluator = AccumulateEvaluator()
    candidates = evaluator.evaluate(
        rule_id="rule-count",
        priority=50,
        working_memory=wm,
        now=now,
        accumulate={
            "over": "Order",
            "aggregate": {"op": "count", "as": "count"},
            "constraint": {"field": "count", "op": ">=", "value": 3},
        },
    )

    assert len(candidates) == 1
    candidate = candidates[0]
    assert candidate["rule_id"] == "rule-count"
    assert candidate["priority"] == 50
    assert candidate["specificity"] == 4
    assert candidate["context"]["accumulate"]["count"] == 4


def test_accumulate_sum_without_group_by() -> None:
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    wm = WorkingMemory()
    _seed_orders(wm, now)

    evaluator = AccumulateEvaluator()
    candidates = evaluator.evaluate(
        rule_id="rule-sum",
        priority=10,
        working_memory=wm,
        now=now,
        accumulate={
            "over": "Order",
            "aggregate": {"op": "sum", "field": "amount", "as": "total_amount"},
            "constraint": {"field": "total_amount", "op": ">", "value": 45},
        },
    )

    assert len(candidates) == 1
    assert candidates[0]["context"]["accumulate"]["total_amount"] == 50.0


def test_accumulate_window_duration_seconds() -> None:
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    wm = WorkingMemory()
    _seed_orders(wm, now)

    evaluator = AccumulateEvaluator()
    candidates = evaluator.evaluate(
        rule_id="rule-window",
        priority=5,
        working_memory=wm,
        now=now,
        accumulate={
            "over": "Order",
            "window": {"duration_seconds": 25},
            "aggregate": {"op": "count", "as": "count"},
        },
    )

    assert len(candidates) == 1
    assert candidates[0]["specificity"] == 2
    assert candidates[0]["context"]["accumulate"]["count"] == 2


def test_accumulate_group_by_with_sum_and_constraint() -> None:
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    wm = WorkingMemory()
    _seed_orders(wm, now)

    evaluator = AccumulateEvaluator()
    candidates = evaluator.evaluate(
        rule_id="rule-group",
        priority=15,
        working_memory=wm,
        now=now,
        accumulate={
            "over": "Order",
            "group_by": "account_id",
            "aggregate": [
                {"op": "count", "as": "count"},
                {"op": "sum", "field": "amount", "as": "sum_amount"},
            ],
            "constraint": {"field": "sum_amount", "op": ">", "value": 20},
        },
    )

    assert len(candidates) == 1
    only = candidates[0]
    assert only["context"]["group"]["account_id"] == "A"
    assert only["context"]["accumulate"]["count"] == 2
    assert only["context"]["accumulate"]["sum_amount"] == 30.0
