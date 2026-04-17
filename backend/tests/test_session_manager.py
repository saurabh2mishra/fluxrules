import threading
import time

import pytest

from app.execution.session_manager import SessionManager


def test_same_session_concurrency_safety():
    manager = SessionManager(cleanup_interval_seconds=60)
    try:
        session = manager.create_session(group="grp", ttl=5, db=None)

        worker_count = 10
        updates_per_worker = 50

        def worker() -> None:
            for i in range(updates_per_worker):
                manager.assert_fact(session.session_id, "same-fact", {"n": i})

        threads = [threading.Thread(target=worker) for _ in range(worker_count)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        fact = manager.get_session(session.session_id).working_memory.facts()["same-fact"]
        assert fact.revision == worker_count * updates_per_worker
    finally:
        manager.close()


def test_cross_session_isolation():
    manager = SessionManager(cleanup_interval_seconds=60)
    try:
        s1 = manager.create_session(group="alpha", ttl=10, db=None)
        s2 = manager.create_session(group="beta", ttl=10, db=None)

        manager.assert_fact(s1.session_id, "customer", {"name": "A"})
        manager.assert_fact(s2.session_id, "customer", {"name": "B"})

        f1 = manager.get_session(s1.session_id).working_memory.facts()["customer"]
        f2 = manager.get_session(s2.session_id).working_memory.facts()["customer"]

        assert f1.payload == {"name": "A"}
        assert f2.payload == {"name": "B"}
    finally:
        manager.close()


def test_max_session_limit(monkeypatch):
    monkeypatch.setattr("app.execution.session_manager.SESSION_MAX_CONCURRENT", 2)
    manager = SessionManager(cleanup_interval_seconds=60)
    try:
        manager.create_session(group="g", ttl=10, db=None)
        manager.create_session(group="g", ttl=10, db=None)

        with pytest.raises(RuntimeError, match="SESSION_MAX_CONCURRENT exceeded"):
            manager.create_session(group="g", ttl=10, db=None)
    finally:
        manager.close()


def test_cleanup_of_expired_sessions():
    manager = SessionManager(cleanup_interval_seconds=0.01)
    try:
        session = manager.create_session(group="g", ttl=0.05, db=None)

        time.sleep(0.15)

        assert manager.get_session(session.session_id) is None
    finally:
        manager.close()
