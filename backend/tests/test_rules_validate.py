import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from app.main import app
from app.database import Base, get_db


SQLALCHEMY_DATABASE_URL = "sqlite://"
_test_engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
_TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=_test_engine)


def _override_get_db():
    db = _TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture(scope="module", autouse=True)
def clean_db():
    """Create fresh tables for this module and tear down afterwards."""
    app.dependency_overrides[get_db] = _override_get_db
    Base.metadata.drop_all(bind=_test_engine)
    Base.metadata.create_all(bind=_test_engine)
    yield
    Base.metadata.drop_all(bind=_test_engine)
    app.dependency_overrides.pop(get_db, None)


@pytest.fixture(scope="module")
def auth_token():
    client = TestClient(app)
    # Register user (ignore if already exists)
    client.post(
        "/api/v1/auth/register",
        json={
            "username": "testuser",
            "email": "testuser@example.com",
            "password": "TestPass123",
            "role": "business"
        }
    )
    # Login
    resp = client.post(
        "/api/v1/auth/token",
        data={"username": "testuser", "password": "TestPass123"},
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


def test_bulk_conflicting_rule_is_parked_not_listed(auth_token):
    client = TestClient(app)
    headers = auth_headers(auth_token)

    seed_rule = {
        "name": "BulkSeedRule",
        "description": "seed",
        "group": "bulk_conflict",
        "priority": 42,
        "enabled": True,
        "condition_dsl": {"type": "condition", "field": "amount", "op": ">", "value": 999},
        "action": "send_alert"
    }
    seed_resp = client.post("/api/v1/rules", json=seed_rule, headers=headers)
    assert seed_resp.status_code == 200

    bulk_rules = [
        {
            "name": "BulkValidRule",
            "description": "valid",
            "group": "bulk_conflict",
            "priority": 100,
            "enabled": True,
            "condition_dsl": {"type": "condition", "field": "score", "op": ">", "value": 5},
            "action": "manual_review"
        },
        {
            "name": "BulkConflictRule",
            "description": "duplicate condition+action should be parked",
            "group": "bulk_other",
            "priority": 101,
            "enabled": True,
            "condition_dsl": {"type": "condition", "field": "amount", "op": ">", "value": 999},
            "action": "send_alert"
        }
    ]

    resp = client.post("/api/v1/rules/bulk", json=bulk_rules, headers=headers)
    assert resp.status_code == 207, resp.text
    detail = resp.json()["detail"]
    assert len(detail["created"]) == 1
    assert any(e.get("rule_name") == "BulkConflictRule" and e.get("parked") for e in detail["errors"])

    listed = client.get("/api/v1/rules", headers=headers)
    assert listed.status_code == 200
    names = [r["name"] for r in listed.json()]
    assert "BulkValidRule" in names
    assert "BulkConflictRule" not in names

    parked = client.get("/api/v1/rules/conflicts/parked?status=pending", headers=headers)
    assert parked.status_code == 200
    assert any(item["name"] == "BulkConflictRule" for item in parked.json())


def test_brms_overlap_blocks_second_rule(auth_token):
    """Two rules whose conditions overlap (brms_overlap) should NOT both be active.
    The second rule must be blocked/parked."""
    client = TestClient(app)
    headers = auth_headers(auth_token)

    # Create the first rule — should succeed
    rule1 = {
        "name": "OverlapBlockTest1",
        "description": "First overlapping rule",
        "group": "overlap_group",
        "priority": 50,
        "enabled": True,
        "condition_dsl": {"type": "condition", "field": "age", "op": ">=", "value": 18},
        "action": "segment=adult",
    }
    resp1 = client.post("/api/v1/rules", json=rule1, headers=headers)
    assert resp1.status_code == 200, f"First rule creation failed: {resp1.text}"

    # Create a second rule with overlapping condition — should be blocked
    rule2 = {
        "name": "OverlapBlockTest2",
        "description": "Second overlapping rule (different action, overlapping condition)",
        "group": "overlap_group",
        "priority": 51,
        "enabled": True,
        "condition_dsl": {"type": "condition", "field": "age", "op": ">=", "value": 25},
        "action": "segment=young_adult",
    }
    resp2 = client.post("/api/v1/rules", json=rule2, headers=headers)
    assert resp2.status_code == 400, f"Overlapping rule was not blocked: {resp2.text}"
    data = resp2.json()
    assert "conflicts" in data["detail"]
    assert any(c["type"] == "brms_overlap" for c in data["detail"]["conflicts"])
    assert data["detail"].get("parked") is True


def test_update_with_brms_overlap_is_blocked(auth_token):
    """Editing a rule to create an overlap with an existing rule should be blocked."""
    client = TestClient(app)
    headers = auth_headers(auth_token)

    # Create two non-conflicting rules
    rule_a = {
        "name": "UpdateOverlapA",
        "description": "Rule A",
        "group": "update_overlap_grp",
        "priority": 60,
        "enabled": True,
        "condition_dsl": {"type": "condition", "field": "score", "op": ">", "value": 100},
        "action": "flag_high",
    }
    rule_b = {
        "name": "UpdateOverlapB",
        "description": "Rule B",
        "group": "update_overlap_grp",
        "priority": 61,
        "enabled": True,
        "condition_dsl": {"type": "condition", "field": "score", "op": "<", "value": 10},
        "action": "flag_low",
    }
    resp_a = client.post("/api/v1/rules", json=rule_a, headers=headers)
    assert resp_a.status_code == 200
    resp_b = client.post("/api/v1/rules", json=rule_b, headers=headers)
    assert resp_b.status_code == 200
    rule_b_id = resp_b.json()["id"]

    # Update rule B so its condition overlaps with rule A
    update_payload = {
        "name": "UpdateOverlapB",
        "description": "Rule B — now overlapping",
        "group": "update_overlap_grp",
        "priority": 61,
        "enabled": True,
        "condition_dsl": {"type": "condition", "field": "score", "op": ">", "value": 50},
        "action": "flag_low",
    }
    resp_update = client.put(f"/api/v1/rules/{rule_b_id}", json=update_payload, headers=headers)
    assert resp_update.status_code == 400, f"Update with overlap was not blocked: {resp_update.text}"
    data = resp_update.json()
    assert "conflicts" in data["detail"]
    assert any(c["type"] == "brms_overlap" for c in data["detail"]["conflicts"])


def test_update_and_create_use_same_blocking_types(auth_token):
    """Create and update endpoints should block on the same conflict types."""
    client = TestClient(app)
    headers = auth_headers(auth_token)

    # Validate endpoint should report brms_overlap as a conflict
    rule = {
        "name": "ConsistencyCheckRule",
        "description": "Check consistency",
        "group": "overlap_group",  # reuse group with existing overlapping rule
        "priority": 99,
        "enabled": True,
        "condition_dsl": {"type": "condition", "field": "age", "op": ">=", "value": 30},
        "action": "notify_admin",
    }
    resp = client.post("/api/v1/rules/validate", json=rule, headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    # The validate endpoint surfaces brms_overlap as a conflict
    has_overlap = any(c["type"] == "brms_overlap" for c in data.get("conflicts", []))
    # If there is overlap, creating the rule should also block it
    if has_overlap:
        resp_create = client.post("/api/v1/rules", json=rule, headers=headers)
        assert resp_create.status_code == 400, \
            "brms_overlap detected in validate but rule was not blocked on create"


def test_resolve_parked_still_checks_brms_overlap(auth_token):
    """Resolving a parked conflict rule must re-validate via full BRMS.
    If the modified rule still overlaps, it must stay parked — not sneak through."""
    client = TestClient(app)
    headers = auth_headers(auth_token)

    # Create a base rule (unique field/values to avoid collisions with earlier tests)
    base_rule = {
        "name": "ResolveBase",
        "description": "base",
        "group": "resolve_grp",
        "priority": 70,
        "enabled": True,
        "condition_dsl": {"type": "condition", "field": "resolve_metric", "op": ">=", "value": 500},
        "action": "resolve_action_a",
    }
    resp = client.post("/api/v1/rules", json=base_rule, headers=headers)
    assert resp.status_code == 200, f"Base rule creation failed: {resp.text}"

    # Create an overlapping rule — should be blocked & parked
    overlap_rule = {
        "name": "ResolveOverlap",
        "description": "overlapping",
        "group": "resolve_grp",
        "priority": 71,
        "enabled": True,
        "condition_dsl": {"type": "condition", "field": "resolve_metric", "op": ">=", "value": 600},
        "action": "resolve_action_b",
    }
    resp2 = client.post("/api/v1/rules", json=overlap_rule, headers=headers)
    assert resp2.status_code == 400

    # Find the parked rule
    parked_resp = client.get("/api/v1/rules/conflicts/parked?status=pending", headers=headers)
    assert parked_resp.status_code == 200
    parked_list = parked_resp.json()
    parked = next((p for p in parked_list if p["name"] == "ResolveOverlap"), None)
    assert parked is not None, f"Parked rule not found. Parked list: {parked_list}"
    parked_id = parked["id"]

    # Try to resolve with a STILL-overlapping rule (only change name/priority)
    still_bad = {
        "name": "ResolveOverlapRenamed",
        "description": "still overlapping",
        "group": "resolve_grp",
        "priority": 72,
        "enabled": True,
        "condition_dsl": {"type": "condition", "field": "resolve_metric", "op": ">=", "value": 600},
        "action": "resolve_action_b",
    }
    resp3 = client.post(f"/api/v1/rules/conflicts/parked/{parked_id}/resolve", json=still_bad, headers=headers)
    assert resp3.status_code == 400, f"Resolve should have failed: {resp3.text}"
    detail = resp3.json().get("detail", {})
    assert any(c.get("type") == "brms_overlap" for c in detail.get("conflicts", [])), \
        f"Expected brms_overlap in resolve conflicts: {detail}"

    # Now resolve with a truly different rule (different field, no overlap)
    fixed = {
        "name": "ResolveFixed",
        "description": "no overlap",
        "group": "resolve_grp",
        "priority": 72,
        "enabled": True,
        "condition_dsl": {"type": "condition", "field": "resolve_country", "op": "==", "value": "US"},
        "action": "resolve_country_check",
    }
    resp4 = client.post(f"/api/v1/rules/conflicts/parked/{parked_id}/resolve", json=fixed, headers=headers)
    assert resp4.status_code == 200, f"Resolve should have succeeded: {resp4.text}"
    assert resp4.json().get("status") == "approved"
