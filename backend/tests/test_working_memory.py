from __future__ import annotations

from app.execution.working_memory import WorkingMemory


def test_fifo_eviction_at_capacity(monkeypatch):
    timestamps = iter([1000.0, 1001.0, 1002.0])
    monkeypatch.setattr("app.execution.working_memory.time.time", lambda: next(timestamps))

    wm = WorkingMemory(max_facts=2)
    wm.insert_fact("f1", {"kind": "alpha"})
    wm.insert_fact("f2", {"kind": "beta"})
    wm.insert_fact("f3", {"kind": "gamma"})

    facts = wm.facts()
    assert "f1" not in facts
    assert "f2" in facts
    assert "f3" in facts
    assert wm.last_evicted is not None
    assert wm.last_evicted.fact_id == "f1"


def test_get_facts_in_time_window(monkeypatch):
    timestamps = iter([1000.0, 1010.0, 1020.0, 1025.0])
    monkeypatch.setattr("app.execution.working_memory.time.time", lambda: next(timestamps))

    wm = WorkingMemory(max_facts=10)
    wm.insert_fact("f1", {"step": 1})
    wm.insert_fact("f2", {"step": 2})
    wm.insert_fact("f3", {"step": 3})

    recent = wm.get_facts_in_window(10)
    assert {fact.fact_id for fact in recent} == {"f3"}


def test_get_facts_by_field():
    wm = WorkingMemory(max_facts=10)
    wm.insert_fact("f1", {"correlation_id": "A-1", "status": "open"})
    wm.insert_fact("f2", {"correlation_id": "A-2", "status": "closed"})
    wm.insert_fact("f3", {"correlation_id": "A-1", "status": "open"})

    correlated = wm.get_facts_by_field("correlation_id", "A-1")
    assert {fact.fact_id for fact in correlated} == {"f1", "f3"}


def test_memory_estimate_grows_with_more_facts():
    wm = WorkingMemory(max_facts=10)
    base = wm.memory_estimate()

    wm.insert_fact("f1", {"payload": "small"})
    one_fact = wm.memory_estimate()

    wm.insert_fact("f2", {"payload": "small", "extra": list(range(100))})
    two_facts = wm.memory_estimate()

    assert base >= 0
    assert one_fact > base
    assert two_facts > one_fact
