"""Unit tests for the Redis event-processing worker.

``process_events`` is an infinite ``brpop`` loop, so the tests drive exactly
one full iteration through mocked dependencies and then raise
``KeyboardInterrupt`` to exit the loop cleanly. All heavy API collaborators
(engine adapter, audit/analytics services, metrics) are monkeypatched on the
worker module namespace.
"""

from __future__ import annotations

import json

import pytest

from fluxrules.api.workers import event_worker as ew


class _FakeDB:
    def __init__(self) -> None:
        self.closed = False

    def close(self) -> None:
        self.closed = True


class _FakeAdapter:
    def __init__(self, *args, **kwargs) -> None:
        pass

    def evaluate(self, data):
        return {"matched_rules": [{"id": 1}], "explanations": {1: "because"}}


class _FakeAudit:
    def __init__(self, db) -> None:
        self.logged: list = []

    def log_action(self, *args, **kwargs) -> None:
        self.logged.append(args)


class _FakeAnalytics:
    def __init__(self) -> None:
        self.rule_executions = 0
        self.events = 0

    def record_rule_execution(self, *args, **kwargs) -> None:
        self.rule_executions += 1

    def record_event_processed(self, *args, **kwargs) -> None:
        self.events += 1


def _install_common(monkeypatch: pytest.MonkeyPatch, db: _FakeDB, analytics: _FakeAnalytics):
    monkeypatch.setattr(ew, "SessionLocal", lambda: db)
    monkeypatch.setattr(ew, "get_analytics_service", lambda: analytics)
    monkeypatch.setattr(ew, "APIEngineAdapter", _FakeAdapter)
    monkeypatch.setattr(ew, "AuditService", _FakeAudit)
    monkeypatch.setattr(ew, "increment_rules_fired", lambda: None)
    monkeypatch.setattr(ew, "increment_events_processed", lambda: None)
    monkeypatch.setattr(ew, "observe_processing_time", lambda *_: None)


def test_process_events_handles_one_event_then_exits(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db = _FakeDB()
    analytics = _FakeAnalytics()
    _install_common(monkeypatch, db, analytics)

    event = json.dumps({"event_id": "e1", "data": {"amount": 5}, "user_id": 3})
    calls = {"n": 0}

    class _FakeRedis:
        def brpop(self, key, timeout=None):
            calls["n"] += 1
            if calls["n"] == 1:
                return ("event_queue", event)
            raise KeyboardInterrupt

    monkeypatch.setattr(ew, "get_redis_client", lambda: _FakeRedis())

    ew.process_events()  # returns after KeyboardInterrupt is caught

    assert analytics.rule_executions == 1
    assert analytics.events == 1
    assert db.closed is True


def test_process_events_skips_empty_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    db = _FakeDB()
    analytics = _FakeAnalytics()
    _install_common(monkeypatch, db, analytics)

    calls = {"n": 0}

    class _EmptyThenStopRedis:
        def brpop(self, key, timeout=None):
            calls["n"] += 1
            if calls["n"] == 1:
                return (None, None)  # empty payload -> continue
            raise KeyboardInterrupt

    monkeypatch.setattr(ew, "get_redis_client", lambda: _EmptyThenStopRedis())

    ew.process_events()

    assert analytics.events == 0
    assert db.closed is True


def test_process_events_sleeps_when_redis_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db = _FakeDB()
    analytics = _FakeAnalytics()
    _install_common(monkeypatch, db, analytics)
    monkeypatch.setattr(ew, "get_redis_client", lambda: None)

    sleeps = {"n": 0}

    def _fake_sleep(_seconds):
        sleeps["n"] += 1
        raise KeyboardInterrupt  # break out of the None-branch loop

    monkeypatch.setattr(ew.time, "sleep", _fake_sleep)

    ew.process_events()

    assert sleeps["n"] == 1
    assert db.closed is True
