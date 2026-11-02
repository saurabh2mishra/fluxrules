"""The in-memory store behind GET /api/v1/explain keeps only recent records."""

from __future__ import annotations

import threading

import pytest

pytest.importorskip("fastapi")

from fluxrules.api.routes.evaluation import _ExecutionStore  # noqa: E402


def _store(limit: int) -> _ExecutionStore:
    return _ExecutionStore(lambda: limit)


def test_oldest_record_is_removed_past_the_limit() -> None:
    store = _store(3)
    for n in range(4):
        store[f"e{n}"] = {"n": n}
    assert "e0" not in store
    assert [store.get(f"e{n}") for n in (1, 2, 3)] == [{"n": 1}, {"n": 2}, {"n": 3}]
    assert len(store) == 3


def test_reading_does_not_keep_a_record() -> None:
    store = _store(2)
    store["e0"] = {}
    store["e1"] = {}
    assert store.get("e0") == {}
    store["e2"] = {}
    assert "e0" not in store


def test_writing_an_id_again_makes_it_newest() -> None:
    store = _store(2)
    store["e0"] = {"v": 1}
    store["e1"] = {}
    store["e0"] = {"v": 2}
    store["e2"] = {}
    assert store.get("e0") == {"v": 2}
    assert "e1" not in store


def test_limit_zero_keeps_nothing() -> None:
    store = _store(0)
    store["e0"] = {}
    assert len(store) == 0
    assert store.get("e0") is None


def test_concurrent_writes_never_exceed_the_limit() -> None:
    store = _store(50)

    def write(prefix: str) -> None:
        for n in range(500):
            store[f"{prefix}{n}"] = {}

    threads = [threading.Thread(target=write, args=(f"t{i}-",)) for i in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert len(store) == 50


def test_limit_is_read_from_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    from fluxrules.api.config import settings
    from fluxrules.api.routes import evaluation

    monkeypatch.setattr(settings, "EXPLAIN_STORE_MAX_RECORDS", 1)
    store = _ExecutionStore(evaluation._explain_store_limit)
    store["e0"] = {}
    store["e1"] = {}
    assert len(store) == 1
