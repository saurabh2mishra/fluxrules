"""Tests for FactStore."""

from __future__ import annotations

import pytest

from fluxrules.engine.infrastructure.fact_store import FactChange, FactEvent, FactStore


class TestFactStoreBasics:
    def test_insert_and_get(self):
        store = FactStore()
        store.insert("age", 30)
        assert store.get("age") == 30
        assert store["age"] == 30
        assert "age" in store
        assert len(store) == 1

    def test_insert_duplicate_raises(self):
        store = FactStore()
        store.insert("age", 30)
        with pytest.raises(KeyError, match="already exists"):
            store.insert("age", 31)

    def test_update(self):
        store = FactStore()
        store.insert("age", 30)
        store.update("age", 31)
        assert store["age"] == 31

    def test_update_missing_raises(self):
        store = FactStore()
        with pytest.raises(KeyError, match="does not exist"):
            store.update("age", 30)

    def test_upsert(self):
        store = FactStore()
        store.upsert("age", 30)
        assert store["age"] == 30
        store.upsert("age", 31)
        assert store["age"] == 31

    def test_retract(self):
        store = FactStore()
        store.insert("age", 30)
        val = store.retract("age")
        assert val == 30
        assert "age" not in store

    def test_retract_missing_raises(self):
        store = FactStore()
        with pytest.raises(KeyError):
            store.retract("age")

    def test_bulk_insert(self):
        store = FactStore()
        store.bulk_insert({"a": 1, "b": 2, "c": 3})
        assert len(store) == 3
        assert store["b"] == 2

    def test_bulk_insert_rollback_on_conflict(self):
        store = FactStore()
        store.insert("a", 1)
        with pytest.raises(KeyError):
            store.bulk_insert({"a": 99, "b": 2})

    def test_clear(self):
        store = FactStore()
        store.bulk_insert({"a": 1, "b": 2})
        store.clear()
        assert len(store) == 0


class TestFactStoreHistory:
    def test_history_recorded(self):
        store = FactStore()
        store.insert("x", 1)
        store.update("x", 2)
        store.retract("x")
        assert len(store.history) == 3
        assert store.history[0].event == FactEvent.INSERTED
        assert store.history[1].event == FactEvent.UPDATED
        assert store.history[1].previous_value == 1
        assert store.history[2].event == FactEvent.RETRACTED

    def test_history_capped(self):
        store = FactStore(max_history=5)
        for i in range(10):
            store.upsert("x", i)
        assert len(store.history) == 5


class TestFactStoreLocking:
    def test_lock_prevents_update(self):
        store = FactStore()
        store.insert("x", 1)
        store.lock("x")
        with pytest.raises(PermissionError):
            store.update("x", 2)

    def test_lock_prevents_retract(self):
        store = FactStore()
        store.insert("x", 1)
        store.lock("x")
        with pytest.raises(PermissionError):
            store.retract("x")

    def test_unlock_allows_update(self):
        store = FactStore()
        store.insert("x", 1)
        store.lock("x")
        store.unlock("x")
        store.update("x", 2)
        assert store["x"] == 2


class TestFactStoreListeners:
    def test_listener_called(self):
        store = FactStore()
        events: list[FactChange] = []
        store.add_listener(events.append)
        store.insert("x", 1)
        assert len(events) == 1
        assert events[0].event == FactEvent.INSERTED

    def test_remove_listener(self):
        store = FactStore()
        events: list[FactChange] = []
        store.add_listener(events.append)
        store.insert("x", 1)
        store.remove_listener(events.append)
        store.update("x", 2)
        assert len(events) == 1


class TestFactStoreSnapshot:
    def test_snapshot_and_restore(self):
        store = FactStore()
        store.insert("a", 1)
        store.insert("b", 2)
        snap = store.snapshot()
        store.update("a", 99)
        store.retract("b")
        store.restore(snap)
        assert store["a"] == 1
        assert store["b"] == 2

    def test_facts_property_is_copy(self):
        store = FactStore()
        store.insert("x", 1)
        facts = store.facts
        facts["x"] = 999
        assert store["x"] == 1


class TestFactStoreIteration:
    def test_iter(self):
        store = FactStore()
        store.bulk_insert({"a": 1, "b": 2, "c": 3})
        assert set(store) == {"a", "b", "c"}
