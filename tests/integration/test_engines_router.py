"""HTTP tests for the engine evaluation router.

Audit 04 (H3) found the engine router imported a symbol that did not exist and
called engines with unsupported keyword arguments, so no request could succeed.
These tests drive the router end to end through the tested APIEngineAdapter for
every selectable engine and assert the response contract, and confirm the
removed INTERPRETER engine is rejected.
"""

from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from fluxrules.api import deps
from fluxrules.api.app import create_app
from fluxrules.api.database import Base, get_db
from fluxrules.api.models.rule import Rule

app = create_app()

engine = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def _fake_user():
    class U:
        id = 1
        username = "testuser"
        email = "t@t.com"
        role = "business"
        is_active = True

    return U()


app.dependency_overrides[deps.get_current_user] = _fake_user
app.dependency_overrides[deps.get_current_admin] = _fake_user


def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = override_get_db


def setup_function():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


def seed_rules():
    db = TestingSessionLocal()
    db.add_all(
        [
            Rule(
                name="high_value",
                group="g1",
                priority=10,
                enabled=True,
                condition_dsl={
                    "type": "condition",
                    "field": "amount",
                    "op": ">",
                    "value": 1000,
                },
                action="review",
                created_by=1,
            ),
            Rule(
                name="small_value",
                group="g1",
                priority=1,
                enabled=True,
                condition_dsl={
                    "type": "condition",
                    "field": "amount",
                    "op": "<",
                    "value": 100,
                },
                action="ignore",
                created_by=1,
            ),
        ]
    )
    db.commit()
    db.close()


def _evaluate(client: TestClient, engine_type: str, amount: float) -> dict:
    response = client.post(
        "/api/v1/engines/evaluate",
        json={"event": {"amount": amount}, "engine_type": engine_type},
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_evaluate_matches_rule_for_phreak():
    seed_rules()
    client = TestClient(app)

    for engine_type in ("PHREAK",):
        matched = _evaluate(client, engine_type, 1500)
        assert matched["engine_type"] == engine_type
        assert matched["dry_run"] is False
        # The high-value rule (amount > 1000) fires; the small-value rule does not.
        # execution_order carries the fired rule IDs.
        assert matched["execution_order"] == [1]

        unmatched = _evaluate(client, engine_type, 500)
        assert unmatched["execution_order"] == []


def test_simulate_sets_dry_run_true():
    seed_rules()
    client = TestClient(app)

    response = client.post(
        "/api/v1/engines/simulate",
        json={"event": {"amount": 1500}, "engine_type": "PHREAK"},
    )
    assert response.status_code == 200, response.text
    assert response.json()["dry_run"] is True


def test_evaluate_rejects_removed_interpreter_engine():
    seed_rules()
    client = TestClient(app)

    response = client.post(
        "/api/v1/engines/evaluate",
        json={"event": {"amount": 1500}, "engine_type": "INTERPRETER"},
    )
    assert response.status_code == 400
    assert "INTERPRETER" in response.json()["detail"]


def test_available_engines_lists_only_phreak():
    client = TestClient(app)
    response = client.get("/api/v1/engines/available")
    assert response.status_code == 200
    assert set(response.json()["available_engines"]) == {"PHREAK"}


def test_benchmark_uses_repeatable_synthetic_events(monkeypatch):
    from fluxrules.api.routes import engines as engine_routes

    evaluated_events = []

    class RecordingEngine:
        def evaluate(self, event):
            evaluated_events.append(event)

    monkeypatch.setattr(engine_routes, "get_engine", lambda engine_type: RecordingEngine())
    client = TestClient(app)

    for _ in range(2):
        response = client.post(
            "/api/v1/engines/benchmark?num_events=3&num_fields=2",
        )
        assert response.status_code == 200, response.text
        assert response.json()["num_events"] == 3

    assert evaluated_events[:6] == evaluated_events[6:]
