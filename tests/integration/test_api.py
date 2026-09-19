import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from fluxrules.api import deps
from fluxrules.api.app import create_app
from fluxrules.api.database import Base, get_db

app = create_app()

SQLALCHEMY_DATABASE_URL = "sqlite://"
test_engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)


def _fake_user():
    class U:
        id = 1
        username = "testuser"
        email = "t@t.com"
        role = "business"
        is_active = True

    return U()


def _fake_admin():
    class U:
        id = 1
        username = "admin"
        email = "a@t.com"
        role = "admin"
        is_active = True

    return U()


app.dependency_overrides[deps.get_current_user] = _fake_user
app.dependency_overrides[deps.get_current_admin] = _fake_admin


@pytest.fixture(autouse=True)
def clean_db():
    Base.metadata.drop_all(bind=test_engine)
    Base.metadata.create_all(bind=test_engine)


def override_get_db():
    try:
        db = TestingSessionLocal()
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = override_get_db

client = TestClient(app)


def test_root():
    response = client.get("/")
    assert response.status_code in (200, 404)  # new API has no root route


def test_health():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "healthy"


def test_register_user():
    response = client.post(
        "/api/v1/auth/register",
        json={
            "username": "testuser3",
            "email": "test3@example.com",
            "password": "TestPass123",
            "role": "business",
        },
    )
    if response.status_code != 200:
        print("Register error:", response.status_code, response.json())
    assert response.status_code == 200
    assert response.json()["username"] == "testuser3"


def test_rule_validate_brms():
    seed_rule = {
        "name": "age_gate_existing",
        "description": "existing",
        "group": "eligibility",
        "priority": 10,
        "enabled": True,
        "condition_dsl": {
            "type": "group",
            "op": "AND",
            "children": [{"type": "condition", "field": "age", "op": ">", "value": 60}],
        },
        "action": "approve",
    }
    create_resp = client.post("/api/v1/rules?skip_conflict_check=true", json=seed_rule)
    assert create_resp.status_code == 200

    candidate_rule = {
        "name": "age_gate_candidate",
        "description": "candidate",
        "group": "eligibility",
        "priority": 11,
        "enabled": True,
        "condition_dsl": {
            "type": "group",
            "op": "AND",
            "children": [{"type": "condition", "field": "age", "op": ">", "value": 65}],
        },
        "action": "manual_review",
    }

    response = client.post(
        "/api/v1/rules/validate",
        json=candidate_rule,
    )
    assert response.status_code == 200
    payload = response.json()
    assert "valid" in payload
    assert "conflicts" in payload
    assert "brms_report" in payload


def test_rule_validate_detects_dead_rule():
    candidate_rule = {
        "name": "brms_contradiction",
        "description": "candidate",
        "group": "eligibility",
        "priority": 5,
        "enabled": True,
        "condition_dsl": {
            "type": "group",
            "op": "AND",
            "children": [
                {"type": "condition", "field": "age", "op": ">", "value": 60},
                {"type": "condition", "field": "age", "op": "<", "value": 50},
            ],
        },
        "action": "manual_review",
    }

    response = client.post(
        "/api/v1/rules/validate",
        json=candidate_rule,
    )
    assert response.status_code == 200
    payload = response.json()
    assert any(c["type"] == "brms_dead_rule" for c in payload["conflicts"])
