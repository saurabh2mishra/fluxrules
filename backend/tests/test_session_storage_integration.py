from __future__ import annotations

from typing import Any, Dict, Iterable

import pytest
from fastapi.testclient import TestClient

from app.execution.session_manager import SessionManager, get_session_manager
from app.execution.session_storage import MemorySessionStorageBackend, RedisSessionStorageBackend
from app.main import app


class FakeRedis:
    def __init__(self) -> None:
        self._store: Dict[str, str] = {}

    def set(self, key: str, value: str) -> None:
        self._store[key] = value

    def get(self, key: str) -> str | None:
        return self._store.get(key)

    def delete(self, key: str) -> int:
        return int(self._store.pop(key, None) is not None)

    def scan_iter(self, pattern: str) -> Iterable[str]:
        if pattern.endswith("*"):
            prefix = pattern[:-1]
            for key in list(self._store.keys()):
                if key.startswith(prefix):
                    yield key
            return
        if pattern in self._store:
            yield pattern


@pytest.fixture(params=["memory", "redis"])
def manager(request: pytest.FixtureRequest) -> SessionManager:
    if request.param == "memory":
        return SessionManager(backend=MemorySessionStorageBackend())
    return SessionManager(backend=RedisSessionStorageBackend(redis_client=FakeRedis(), prefix="test_sess"))


def _exercise_manager(manager: SessionManager) -> Dict[str, Any]:
    created = manager.create_session(session_id="s-1", metadata={"source": "itest"})
    assert created.session_id == "s-1"

    manager.assert_fact("s-1", "f-1", {"value": 1})
    manager.assert_fact("s-1", "f-2", {"value": 2})
    manager.assert_fact("s-1", "f-2", {"value": 22})

    session = manager.get_session("s-1")
    assert session is not None
    before_retract = session.to_dict()

    retracted = manager.retract_fact("s-1", "f-1")
    assert retracted is True
    retract_missing = manager.retract_fact("s-1", "missing")
    assert retract_missing is False

    after_retract = manager.get_session("s-1")
    assert after_retract is not None

    listing = sorted([ctx.session_id for ctx in manager.list_sessions()])
    deleted = manager.delete_session("s-1")
    deleted_missing = manager.delete_session("s-1")

    return {
        "before": before_retract,
        "after": after_retract.to_dict(),
        "listing": listing,
        "deleted": deleted,
        "deleted_missing": deleted_missing,
    }


def test_manager_behavior_parity(manager: SessionManager):
    snapshot = _exercise_manager(manager)

    assert snapshot["before"]["facts"] == {"f-1": {"value": 1}, "f-2": {"value": 22}}
    assert snapshot["after"]["facts"] == {"f-2": {"value": 22}}
    assert snapshot["listing"] == ["s-1"]
    assert snapshot["deleted"] is True
    assert snapshot["deleted_missing"] is False


def test_session_routes_operate_via_manager_apis(manager: SessionManager):
    app.dependency_overrides[get_session_manager] = lambda: manager
    try:
        with TestClient(app) as client:
            create = client.post("/api/v1/sessions", json={"session_id": "api-1", "metadata": {"x": 1}})
            assert create.status_code == 200

            assert_fact = client.post(
                "/api/v1/sessions/api-1/facts",
                json={"fact_id": "f-1", "payload": {"x": "y"}},
            )
            assert assert_fact.status_code == 200

            read = client.get("/api/v1/sessions/api-1")
            assert read.status_code == 200
            assert read.json()["facts"] == {"f-1": {"x": "y"}}

            retract = client.delete("/api/v1/sessions/api-1/facts/f-1")
            assert retract.status_code == 200

            list_resp = client.get("/api/v1/sessions")
            assert list_resp.status_code == 200
            assert any(item["session_id"] == "api-1" for item in list_resp.json())

            delete = client.delete("/api/v1/sessions/api-1")
            assert delete.status_code == 200

            missing = client.get("/api/v1/sessions/api-1")
            assert missing.status_code == 404
    finally:
        app.dependency_overrides.pop(get_session_manager, None)
