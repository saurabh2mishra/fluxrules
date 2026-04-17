import pytest
from fastapi.testclient import TestClient

from app.api import deps
from app.api.routes import sessions as sessions_route
from app.main import app

client = TestClient(app)


@pytest.fixture(autouse=True)
def _reset_store() -> None:
    sessions_route.reset_session_store()


def _create_session() -> str:
    response = client.post("/api/v1/sessions", json={"metadata": {"source": "test"}})
    assert response.status_code == 201
    return response.json()["id"]


def test_session_lifecycle() -> None:
    session_id = _create_session()

    create_fact = client.post(
        f"/api/v1/sessions/{session_id}/facts",
        json={"fact": {"age": 33, "region": "US"}},
    )
    assert create_fact.status_code == 201
    fact_id = create_fact.json()["fact_id"]

    get_session = client.get(f"/api/v1/sessions/{session_id}")
    assert get_session.status_code == 200
    assert get_session.json()["total_facts"] == 1

    list_facts = client.get(f"/api/v1/sessions/{session_id}/facts")
    assert list_facts.status_code == 200
    assert len(list_facts.json()) == 1
    assert list_facts.json()[0]["fact"]["age"] == 33

    delete_fact = client.delete(f"/api/v1/sessions/{session_id}/facts/{fact_id}")
    assert delete_fact.status_code == 204

    list_facts_after = client.get(f"/api/v1/sessions/{session_id}/facts")
    assert list_facts_after.status_code == 200
    assert list_facts_after.json() == []

    delete_session = client.delete(f"/api/v1/sessions/{session_id}")
    assert delete_session.status_code == 204

    get_deleted = client.get(f"/api/v1/sessions/{session_id}")
    assert get_deleted.status_code == 404


def test_session_endpoints_require_auth() -> None:
    original = app.dependency_overrides.get(deps.get_current_user)
    app.dependency_overrides.pop(deps.get_current_user, None)
    try:
        response = client.post("/api/v1/sessions", json={"metadata": {}})
        assert response.status_code in (401, 403)
    finally:
        if original is not None:
            app.dependency_overrides[deps.get_current_user] = original


def test_session_404s() -> None:
    missing_session = "missing-session"

    response = client.get(f"/api/v1/sessions/{missing_session}")
    assert response.status_code == 404

    response = client.post(
        f"/api/v1/sessions/{missing_session}/facts",
        json={"fact": {"k": "v"}},
    )
    assert response.status_code == 404

    session_id = _create_session()
    response = client.delete(f"/api/v1/sessions/{session_id}/facts/missing-fact")
    assert response.status_code == 404


def test_session_fact_limit_returns_429(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sessions_route, "MAX_FACTS_PER_SESSION", 1)
    session_id = _create_session()

    first = client.post(f"/api/v1/sessions/{session_id}/facts", json={"fact": {"a": 1}})
    assert first.status_code == 201

    second = client.post(f"/api/v1/sessions/{session_id}/facts", json={"fact": {"a": 2}})
    assert second.status_code == 429
