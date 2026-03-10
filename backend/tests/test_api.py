import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.database import Base, engine, get_db
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

@pytest.fixture(autouse=True)
def clean_db():
    Base.metadata.drop_all(bind=test_engine)
    Base.metadata.create_all(bind=test_engine)
    

SQLALCHEMY_DATABASE_URL = "sqlite:///./test.db"
test_engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)

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
    assert response.status_code == 200
    # Root now serves HTML frontend
    assert "<!DOCTYPE html>" in response.text or "message" in response.text

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
            "password": "testpass123",
            "role": "business"
        }
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
        "action": "approve"
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
        "action": "manual_review"
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
                {"type": "condition", "field": "age", "op": "<", "value": 50}
            ],
        },
        "action": "manual_review"
    }

    response = client.post(
        "/api/v1/rules/validate",
        json=candidate_rule,
    )
    assert response.status_code == 200
    payload = response.json()
    assert any(c["type"] == "brms_dead_rule" for c in payload["conflicts"])
