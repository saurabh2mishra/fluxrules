import pytest

from app.execution.storage_backend import MemorySessionStorage


class ManualClock:
    def __init__(self, initial: float = 0.0):
        self._now = initial

    def __call__(self) -> float:
        return self._now

    def advance(self, seconds: float) -> None:
        self._now += seconds


def test_create_and_destroy_session():
    storage = MemorySessionStorage(default_ttl_seconds=30)

    assert storage.create_session("s1") is True
    assert storage.create_session("s1") is False
    assert storage.destroy_session("s1") is True
    assert storage.destroy_session("s1") is False


def test_fact_assert_retract_and_get_returns_copy():
    storage = MemorySessionStorage(default_ttl_seconds=None)
    storage.create_session("s1")

    storage.assert_fact("s1", "f1", {"status": "active"})
    facts = storage.get_facts("s1")
    assert facts == {"f1": {"status": "active"}}

    facts["f1"]["status"] = "mutated"
    assert storage.get_facts("s1")["f1"]["status"] == "active"

    assert storage.retract_fact("s1", "f1") is True
    assert storage.retract_fact("s1", "f1") is False


def test_accumulate_counter_operations():
    storage = MemorySessionStorage(default_ttl_seconds=None)
    storage.create_session("s1")

    assert storage.accumulate_counter("s1", "hits") == 1
    assert storage.accumulate_counter("s1", "hits", delta=4) == 5
    assert storage.accumulate_counter("s1", "hits", delta=-2) == 3


def test_sequence_operations():
    storage = MemorySessionStorage(default_ttl_seconds=None)
    storage.create_session("s1")

    assert storage.next_sequence("s1", "invoice") == 0
    assert storage.next_sequence("s1", "invoice") == 1
    assert storage.next_sequence("s1", "invoice", step=10) == 11

    assert storage.next_sequence("s1", "batch", start=100, step=5) == 100
    assert storage.next_sequence("s1", "batch", step=5) == 105


def test_unknown_session_raises_key_error():
    storage = MemorySessionStorage(default_ttl_seconds=None)

    with pytest.raises(KeyError):
        storage.get_facts("missing")


def test_sessions_expire_with_ttl():
    clock = ManualClock(initial=100)
    storage = MemorySessionStorage(default_ttl_seconds=10, time_fn=clock)

    storage.create_session("s1")
    storage.assert_fact("s1", "f1", {"ok": True})

    clock.advance(9)
    assert storage.get_facts("s1") == {"f1": {"ok": True}}

    clock.advance(11)
    with pytest.raises(KeyError):
        storage.get_facts("s1")


def test_session_specific_ttl_override():
    clock = ManualClock(initial=0)
    storage = MemorySessionStorage(default_ttl_seconds=60, time_fn=clock)

    storage.create_session("short", ttl_seconds=5)
    clock.advance(6)

    with pytest.raises(KeyError):
        storage.get_facts("short")
