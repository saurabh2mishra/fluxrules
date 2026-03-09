import pytest
from fastapi.testclient import TestClient
from app.main import app

@pytest.fixture(scope="module")
def auth_token():
    client = TestClient(app)
    # Register user (ignore if already exists)
    client.post(
        "/api/v1/auth/register",
        json={
            "username": "testuser",
            "email": "testuser@example.com",
            "password": "testpass123",
            "role": "business"
        }
    )
    # Login
    resp = client.post(
        "/api/v1/auth/token",
        data={"username": "testuser", "password": "testpass123"},
        headers={"Content-Type": "application/x-www-form-urlencoded"}
    )
    assert resp.status_code == 200, f"Login failed: {resp.text}"
    token = resp.json()["access_token"]
    return token


def auth_headers(token):
    return {"Authorization": f"Bearer {token}"}


def test_validate_rule_duplicate_name(auth_token):
    client = TestClient(app)
    headers = auth_headers(auth_token)
    # Create a rule
    rule = {
        "name": "UniqueNameTest",
        "description": "desc",
        "group": "g1",
        "priority": 1,
        "enabled": True,
        "condition_dsl": {"type": "condition", "field": "amount", "op": ">", "value": 100},
        "action": "print('ok')"
    }
    resp1 = client.post("/api/v1/rules", json=rule, headers=headers)
    assert resp1.status_code == 200
    # Validate with same name (should get duplicate_name conflict)
    resp2 = client.post("/api/v1/rules/validate", json=rule, headers=headers)
    assert resp2.status_code == 200
    data = resp2.json()
    assert any(c["type"] == "duplicate_name" for c in data["conflicts"])


def test_validate_rule_priority_collision(auth_token):
    client = TestClient(app)
    headers = auth_headers(auth_token)
    # Create two rules with same group/priority
    rule1 = {
        "name": "PriorityTest1",
        "description": "desc",
        "group": "g2",
        "priority": 5,
        "enabled": True,
        "condition_dsl": {"type": "condition", "field": "score", "op": ">", "value": 50},
        "action": "flag_for_review"
    }
    rule2 = dict(rule1)
    rule2["name"] = "PriorityTest2"
    rule2["condition_dsl"] = {"type": "condition", "field": "score", "op": ">", "value": 51}
    resp1 = client.post("/api/v1/rules", json=rule1, headers=headers)
    assert resp1.status_code == 200
    resp2 = client.post("/api/v1/rules", json=rule2, headers=headers)
    # Should fail with 400 due to priority collision
    assert resp2.status_code == 400
    data = resp2.json()
    assert "conflicts" in data["detail"]
    assert any(c["type"] == "priority_collision" for c in data["detail"]["conflicts"])


def test_validate_rule_edit_self_no_conflict(auth_token):
    client = TestClient(app)
    headers = auth_headers(auth_token)
    # Create a rule
    rule = {
        "name": "EditSelfTest",
        "description": "desc",
        "group": "g3",
        "priority": 7,
        "enabled": True,
        "condition_dsl": {"type": "condition", "field": "temperature", "op": ">", "value": 200},
        "action": "send_email"
    }
    resp1 = client.post("/api/v1/rules", json=rule, headers=headers)
    assert resp1.status_code == 200
    rule_id = resp1.json()["id"]
    # Validate with rule_id (should NOT get duplicate_name or priority_collision with self)
    resp2 = client.post(f"/api/v1/rules/validate?rule_id={rule_id}", json=rule, headers=headers)
    assert resp2.status_code == 200
    data = resp2.json()
    assert not any(c["type"] in ("duplicate_name", "priority_collision", "duplicate_condition") and c.get("existing_rule_id") == rule_id for c in data["conflicts"])


def test_duplicate_condition_and_action_blocked(auth_token):
    """Rules with identical condition AND action should be parked, even across different groups."""
    client = TestClient(app)
    headers = auth_headers(auth_token)
    # Create a rule
    rule1 = {
        "name": "DupCondTest1",
        "description": "first rule",
        "group": "dup_group_a",
        "priority": 10,
        "enabled": True,
        "condition_dsl": {"type": "group", "op": "AND", "children": [
            {"type": "condition", "field": "age", "op": ">", "value": 18}
        ]},
        "action": "send_alert"
    }
    resp1 = client.post("/api/v1/rules", json=rule1, headers=headers)
    assert resp1.status_code == 200, f"First rule creation failed: {resp1.text}"

    # Create a second rule with same condition + action but different group/priority/name
    rule2 = {
        "name": "DupCondTest2",
        "description": "second rule, same logic",
        "group": "dup_group_b",
        "priority": 20,
        "enabled": True,
        "condition_dsl": {"type": "group", "op": "AND", "children": [
            {"type": "condition", "field": "age", "op": ">", "value": 18}
        ]},
        "action": "send_alert"
    }
    resp2 = client.post("/api/v1/rules", json=rule2, headers=headers)
    # Should be blocked with 400 and parked as duplicate_condition
    assert resp2.status_code == 400, f"Duplicate rule was not blocked: {resp2.text}"
    data = resp2.json()
    assert "conflicts" in data["detail"]
    assert any(c["type"] == "duplicate_condition" for c in data["detail"]["conflicts"])
    assert data["detail"].get("parked") is True


def test_same_condition_different_action_not_blocked(auth_token):
    """Rules with same condition but different action should NOT be flagged as duplicate."""
    client = TestClient(app)
    headers = auth_headers(auth_token)
    rule = {
        "name": "DiffActionTest",
        "description": "same condition, different action",
        "group": "diff_action_group",
        "priority": 30,
        "enabled": True,
        "condition_dsl": {"type": "group", "op": "AND", "children": [
            {"type": "condition", "field": "age", "op": ">", "value": 18}
        ]},
        "action": "block_transaction"
    }
    resp = client.post("/api/v1/rules", json=rule, headers=headers)
    assert resp.status_code == 200, f"Rule with different action was incorrectly blocked: {resp.text}"
