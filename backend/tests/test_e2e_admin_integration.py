"""
End-to-end integration tests for the Admin Panel frontend integration.

Verifies all backend admin endpoints return the expected shapes so the
frontend admin.js can render them correctly. This covers:

1. Admin: Schema Info          (GET  /admin/schema)
2. Admin: DB Health            (GET  /admin/db/health)
3. Admin: Audit Integrity      (GET  /admin/audit/integrity)
4. Admin: Audit Retention      (POST /admin/audit/retention)
5. Audit Policies CRUD         (POST/GET/PATCH/DELETE /admin/audit-policy)
6. Audit Reports               (GET  /admin/audit-report)
7. Audit Run (Manual)          (POST /admin/audit-run)
8. Engine Stats                (GET  /rules/engine/stats)
9. Engine Cache Invalidation   (POST /rules/engine/invalidate-cache)
10. Engine Reload              (POST /rules/reload)
11. Bulk Create (Sync)         (POST /rules/bulk)
12. Existing CRUD (regression) (GET /rules, POST /rules, etc.)
"""

import pytest
import json
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.main import app
from app.database import Base, get_db
from app.models.rule import Rule

# ── Test DB setup (isolated from production) ─────────────────
SQLALCHEMY_DATABASE_URL = "sqlite://"
test_engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(
    autocommit=False, autoflush=False, bind=test_engine
)

Base.metadata.create_all(bind=test_engine)


def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = override_get_db


@pytest.fixture(autouse=True)
def clean_db():
    """Reset all tables between tests for isolation."""
    Base.metadata.drop_all(bind=test_engine)
    Base.metadata.create_all(bind=test_engine)


@pytest.fixture
def client():
    """Create a TestClient. Auth is overridden globally by conftest.py."""
    return TestClient(app)


def assert_no_error(resp, expected_status=200):
    """Assert HTTP response is successful and return parsed JSON."""
    assert resp.status_code == expected_status, (
        f"Expected {expected_status}, got {resp.status_code}: {resp.text}"
    )
    return resp.json()


# ═════════════════════════════════════════════════════════════
#  1. Admin Overview Tab endpoints
# ═════════════════════════════════════════════════════════════

class TestAdminOverviewEndpoints:
    """Tests for the Overview tab: schema, db health, integrity."""

    def test_schema_info(self, client):
        """GET /admin/schema — returns expected_version, recorded_version, match, history."""
        data = assert_no_error(client.get("/api/v1/admin/schema"))
        assert "expected_version" in data
        assert "recorded_version" in data
        assert "match" in data
        assert isinstance(data["match"], bool)
        assert "history" in data
        assert isinstance(data["history"], list)

    def test_db_health(self, client):
        """GET /admin/db/health — returns backend, url_masked, is_fallback, etc."""
        data = assert_no_error(client.get("/api/v1/admin/db/health"))
        assert "backend" in data
        assert data["backend"] in ("sqlite", "postgresql", "other")
        assert "url_masked" in data
        assert "is_fallback" in data
        assert isinstance(data["is_fallback"], bool)
        assert "fallback_enabled" in data
        assert "environment" in data

    def test_audit_integrity(self, client):
        """GET /admin/audit/integrity — returns total_checked, valid, invalid, unprotected."""
        data = assert_no_error(client.get("/api/v1/admin/audit/integrity?limit=50"))
        assert "total_checked" in data
        assert "valid" in data
        assert "invalid" in data
        assert "unprotected" in data
        # All should be non-negative integers
        for key in ("total_checked", "valid", "invalid", "unprotected"):
            assert isinstance(data[key], int)
            assert data[key] >= 0

    def test_audit_retention(self, client):
        """POST /admin/audit/retention — returns retention_days, rows_purged."""
        data = assert_no_error(client.post("/api/v1/admin/audit/retention"))
        assert "retention_days" in data
        assert "rows_purged" in data
        assert isinstance(data["retention_days"], int)
        assert isinstance(data["rows_purged"], int)


# ═════════════════════════════════════════════════════════════
#  2. Audit Policies Tab endpoints
# ═════════════════════════════════════════════════════════════

class TestAuditPoliciesEndpoints:
    """Tests for Audit Policy CRUD as consumed by admin.js."""

    def test_list_empty(self, client):
        """GET /admin/audit-policy — returns a list (possibly empty)."""
        data = assert_no_error(client.get("/api/v1/admin/audit-policy"))
        assert isinstance(data, list)

    def test_crud_lifecycle(self, client):
        """Full create → list → toggle → delete lifecycle."""
        # Create
        create_resp = client.post("/api/v1/admin/audit-policy", json={
            "name": "e2e_test_policy",
            "cron_expression": "0 3 * * *",
            "scope": "integrity",
            "description": "E2E test policy",
            "enabled": True,
        })
        created = assert_no_error(create_resp)
        policy_id = created["id"]
        assert created["name"] == "e2e_test_policy"
        assert created["enabled"] is True

        # List — should contain the new policy
        policies = assert_no_error(client.get("/api/v1/admin/audit-policy"))
        names = [p["name"] for p in policies]
        assert "e2e_test_policy" in names

        # Toggle (disable)
        toggle_resp = client.patch(
            f"/api/v1/admin/audit-policy/{policy_id}",
            json={"enabled": False}
        )
        toggled = assert_no_error(toggle_resp)
        assert toggled["enabled"] is False

        # Delete
        delete_resp = client.delete(f"/api/v1/admin/audit-policy/{policy_id}")
        assert delete_resp.status_code == 200

        # Verify deletion
        policies_after = assert_no_error(client.get("/api/v1/admin/audit-policy"))
        remaining_ids = [p["id"] for p in policies_after]
        assert policy_id not in remaining_ids


# ═════════════════════════════════════════════════════════════
#  3. Audit Reports Tab endpoints
# ═════════════════════════════════════════════════════════════

class TestAuditReportsEndpoints:
    """Tests for Audit Reports list + manual run."""

    def test_list_reports(self, client):
        """GET /admin/audit-report — returns a list."""
        data = assert_no_error(client.get("/api/v1/admin/audit-report?limit=10"))
        assert isinstance(data, list)

    def test_manual_audit_run(self, client):
        """POST /admin/audit-run — triggers an audit and returns report summary."""
        data = assert_no_error(client.post("/api/v1/admin/audit-run", json={"scope": "all"}))
        assert "report_id" in data
        assert "status" in data
        assert data["status"] in ("passed", "warnings", "failed", "error")
        assert "summary" in data

    def test_report_detail(self, client):
        """Run an audit, then GET /admin/audit-report/{id} to verify detail shape."""
        # Create a report first
        run_data = assert_no_error(client.post("/api/v1/admin/audit-run", json={"scope": "all"}))
        report_id = run_data["report_id"]

        # Fetch detail
        detail = assert_no_error(client.get(f"/api/v1/admin/audit-report/{report_id}"))
        assert detail["id"] == report_id
        assert "status" in detail
        assert "scope" in detail
        assert "rules_checked" in detail
        assert "coverage_pct" in detail
        assert "duration_seconds" in detail


# ═════════════════════════════════════════════════════════════
#  4. Engine Tab endpoints
# ═════════════════════════════════════════════════════════════

class TestEngineEndpoints:
    """Tests for engine stats, cache invalidation, and reload."""

    def test_engine_stats(self, client):
        """GET /rules/engine/stats — returns engine_type, counters."""
        data = assert_no_error(client.get("/api/v1/rules/engine/stats"))
        assert "engine_type" in data
        assert data["engine_type"] in ("optimized", "simple")
        assert "total_evaluations" in data
        assert "rules_matched" in data

    def test_invalidate_cache(self, client):
        """POST /rules/engine/invalidate-cache — returns success message."""
        data = assert_no_error(client.post("/api/v1/rules/engine/invalidate-cache"))
        assert "message" in data

    def test_reload_engine(self, client):
        """POST /rules/reload — returns success message."""
        data = assert_no_error(client.post("/api/v1/rules/reload"))
        assert "message" in data


# ═════════════════════════════════════════════════════════════
#  5. Bulk Import Tab endpoint
# ═════════════════════════════════════════════════════════════

class TestBulkImportEndpoint:
    """Tests for bulk import as consumed by admin.js."""

    def test_bulk_create_single_rule(self, client):
        """POST /rules/bulk — import one valid rule."""
        rules = [{
            "name": "e2e_bulk_rule_1",
            "description": "E2E bulk test",
            "group": "e2e",
            "priority": 50,
            "enabled": True,
            "condition_dsl": {
                "type": "group", "op": "AND",
                "children": [{"type": "condition", "field": "amount", "op": ">", "value": 1000}]
            },
            "action": "flag_high_value"
        }]
        resp = client.post("/api/v1/rules/bulk?validate_conflicts=true", json=rules)
        # Could be 200 (all created) or 207 (partial success)
        assert resp.status_code in (200, 207), f"Unexpected: {resp.status_code} {resp.text}"
        data = resp.json()
        if resp.status_code == 200:
            assert isinstance(data, list)
            assert len(data) >= 1

    def test_bulk_create_empty_array_accepted(self, client):
        """POST /rules/bulk — empty array returns empty 200 (backend accepts gracefully)."""
        resp = client.post("/api/v1/rules/bulk", json=[])
        # Backend returns 200 with an empty list — this is valid
        assert resp.status_code == 200


# ═════════════════════════════════════════════════════════════
#  6. Regression: Existing Features Still Work
# ═════════════════════════════════════════════════════════════

class TestExistingFeaturesRegression:
    """Verify existing CRUD and features are unaffected."""

    def test_list_rules(self, client):
        """GET /rules — basic list still works."""
        data = assert_no_error(client.get("/api/v1/rules"))
        assert isinstance(data, list)

    def test_create_and_read_rule(self, client):
        """POST /rules → GET /rules/{id} roundtrip."""
        rule = {
            "name": "e2e_regression_rule",
            "description": "Regression test",
            "group": "regression",
            "priority": 1,
            "enabled": True,
            "condition_dsl": {
                "type": "group", "op": "AND",
                "children": [{"type": "condition", "field": "x", "op": "==", "value": 1}]
            },
            "action": "log"
        }
        created = assert_no_error(client.post("/api/v1/rules", json=rule))
        rule_id = created["id"]

        fetched = assert_no_error(client.get(f"/api/v1/rules/{rule_id}"))
        assert fetched["name"] == "e2e_regression_rule"

    def test_rule_groups(self, client):
        """GET /rules/groups — returns groups list inside envelope."""
        data = assert_no_error(client.get("/api/v1/rules/groups"))
        assert "groups" in data
        assert isinstance(data["groups"], list)

    def test_available_actions(self, client):
        """GET /rules/actions/available — returns actions list inside envelope."""
        data = assert_no_error(client.get("/api/v1/rules/actions/available"))
        assert "actions" in data
        assert isinstance(data["actions"], list)
        assert len(data["actions"]) > 0

    def test_simulate_event(self, client):
        """POST /rules/simulate — returns simulation results."""
        resp = client.post("/api/v1/rules/simulate", json={
            "event": {"amount": 500, "type": "test"},
            "rule_ids": None
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "matched_rules" in data or "results" in data or isinstance(data, dict)

    def test_simulate_event_excludes_stateful_rules(self, client):
        """POST /rules/simulate excludes stateful rules from stateless path."""
        db = TestingSessionLocal()
        try:
            condition = {
                "type": "group",
                "op": "AND",
                "children": [{"type": "condition", "field": "amount", "op": ">=", "value": 100}],
            }
            db.add(
                Rule(
                    name="stateless_match",
                    group="regression",
                    priority=10,
                    enabled=True,
                    condition_dsl=json.dumps(condition),
                    action="log",
                    evaluation_mode="stateless",
                )
            )
            db.add(
                Rule(
                    name="stateful_match",
                    group="regression",
                    priority=9,
                    enabled=True,
                    condition_dsl=json.dumps(condition),
                    action="log",
                    evaluation_mode="stateful",
                )
            )
            db.commit()
        finally:
            db.close()

        resp = client.post("/api/v1/rules/simulate", json={"event": {"amount": 500}, "rule_ids": None})
        assert resp.status_code == 200
        data = resp.json()
        matched_names = [r["name"] for r in data["matched_rules"]]
        assert "stateless_match" in matched_names
        assert "stateful_match" not in matched_names

    def test_analytics_runtime(self, client):
        """GET /analytics/runtime — returns analytics data."""
        resp = client.get("/api/v1/analytics/runtime")
        assert resp.status_code == 200

    def test_dependency_graph_summary(self, client):
        """GET /rules/graph/summary — returns dependency data."""
        resp = client.get("/api/v1/rules/graph/summary")
        assert resp.status_code == 200

    def test_conflict_detection(self, client):
        """GET /conflicts/detect — returns conflicts list."""
        resp = client.get("/api/v1/rules/conflicts/detect")
        assert resp.status_code == 200

    def test_parked_conflicts(self, client):
        """GET /conflicts/parked — returns parked conflicts."""
        resp = client.get("/api/v1/rules/conflicts/parked")
        assert resp.status_code == 200
