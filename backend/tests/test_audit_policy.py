"""Comprehensive tests for the production audit-policy system.

Covers:
  - Unit tests for cron parsing, scope resolution, report hashing
  - Audit runner: integrity, retention, coverage, rule_health, performance
  - Audit policy CRUD via API
  - Manual audit-run trigger via API
  - Audit report listing and detail retrieval
  - Scheduler start/stop lifecycle
  - E2E flows: create policy → trigger run → verify report
  - Performance benchmarks for audit operations
  - Backward compatibility: existing admin endpoints unchanged
"""

import json
import os
import time
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

# ---------------------------------------------------------------------------
# Test infrastructure
# ---------------------------------------------------------------------------

SQLALCHEMY_DATABASE_URL = "sqlite://"
test_engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(
    autocommit=False, autoflush=False, bind=test_engine
)

from app.main import app
from app.database import Base, get_db
from app.api import deps


def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


class FakeAdmin:
    id = 1
    username = "admin"
    email = "admin@example.com"
    role = "admin"
    is_active = True


class FakeUser:
    id = 2
    username = "regular"
    email = "user@example.com"
    role = "business"
    is_active = True


@pytest.fixture(autouse=True)
def _reset_db():
    """Recreate tables for every test so state never leaks."""
    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[deps.get_current_user] = lambda: FakeUser()
    app.dependency_overrides[deps.get_current_admin] = lambda: FakeAdmin()
    Base.metadata.drop_all(bind=test_engine)
    with test_engine.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS schema_meta"))
        conn.execute(text("DROP TABLE IF EXISTS alembic_version"))
    Base.metadata.create_all(bind=test_engine)
    yield
    Base.metadata.drop_all(bind=test_engine)
    with test_engine.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS schema_meta"))
        conn.execute(text("DROP TABLE IF EXISTS alembic_version"))


client = TestClient(app)


def _unique(prefix: str = "policy") -> str:
    return f"{prefix}_{uuid.uuid4().hex[:8]}"


# ===================================================================
# 1. UNIT TESTS — Cron parser
# ===================================================================


class TestCronParser:
    """Unit tests for the built-in cron expression parser."""

    def test_parse_star(self):
        from app.services.audit_scheduler import _parse_cron_field
        result = _parse_cron_field("*", 0, 59)
        assert result == list(range(0, 60))

    def test_parse_step(self):
        from app.services.audit_scheduler import _parse_cron_field
        result = _parse_cron_field("*/15", 0, 59)
        assert result == [0, 15, 30, 45]

    def test_parse_exact(self):
        from app.services.audit_scheduler import _parse_cron_field
        result = _parse_cron_field("5", 0, 59)
        assert result == [5]

    def test_parse_range(self):
        from app.services.audit_scheduler import _parse_cron_field
        result = _parse_cron_field("1-5", 0, 59)
        assert result == [1, 2, 3, 4, 5]

    def test_parse_list(self):
        from app.services.audit_scheduler import _parse_cron_field
        result = _parse_cron_field("1,15,30", 0, 59)
        assert result == [1, 15, 30]

    def test_compute_next_run_daily_2am(self):
        from datetime import datetime
        from app.services.audit_scheduler import compute_next_run
        after = datetime(2026, 3, 26, 1, 0, 0)
        nxt = compute_next_run("0 2 * * *", after=after)
        assert nxt.hour == 2
        assert nxt.minute == 0
        assert nxt >= after

    def test_compute_next_run_advances_past_current(self):
        from datetime import datetime
        from app.services.audit_scheduler import compute_next_run
        after = datetime(2026, 3, 26, 2, 30, 0)
        nxt = compute_next_run("0 2 * * *", after=after)
        # Should be next day 2 AM since we're already past 2:00 today
        assert nxt.day == 27
        assert nxt.hour == 2

    def test_invalid_cron_fields_raises(self):
        from app.services.audit_scheduler import compute_next_run
        with pytest.raises(ValueError, match="5 fields"):
            compute_next_run("0 2 * *")  # only 4 fields

    def test_weekday_mapping(self):
        from app.services.audit_scheduler import _cron_weekday_to_python
        # Cron: 0=Sun, Python: 6=Sun
        result = _cron_weekday_to_python([0])
        assert 6 in result
        # Cron: 1=Mon, Python: 0=Mon
        result = _cron_weekday_to_python([1])
        assert 0 in result


# ===================================================================
# 2. UNIT TESTS — Scope resolution
# ===================================================================


class TestScopeResolution:
    """Unit tests for audit scope parsing and validation."""

    def test_all_expands_to_all_checks(self):
        from app.services.audit_runner import _resolve_scopes
        scopes = _resolve_scopes("all")
        assert "integrity" in scopes
        assert "retention" in scopes
        assert "coverage" in scopes
        assert "rule_health" in scopes
        assert "performance" in scopes
        assert "all" not in scopes

    def test_specific_scopes(self):
        from app.services.audit_runner import _resolve_scopes
        scopes = _resolve_scopes("integrity,coverage")
        assert scopes == ["coverage", "integrity"]

    def test_unknown_scope_raises(self):
        from app.services.audit_runner import _resolve_scopes
        with pytest.raises(ValueError, match="Unknown audit scope"):
            _resolve_scopes("integrity,bogus_scope")

    def test_duplicate_scopes_deduplicated(self):
        from app.services.audit_runner import _resolve_scopes
        scopes = _resolve_scopes("integrity,integrity,coverage")
        assert scopes == ["coverage", "integrity"]


# ===================================================================
# 3. UNIT TESTS — Report integrity hash
# ===================================================================


class TestReportHash:
    """Unit tests for audit-report HMAC-SHA256 integrity hashing."""

    def test_hash_is_deterministic(self):
        from datetime import datetime
        from app.services.audit_runner import _compute_report_hash
        ts = datetime(2026, 3, 26, 12, 0, 0)
        h1 = _compute_report_hash("all", "passed", "{}", ts)
        h2 = _compute_report_hash("all", "passed", "{}", ts)
        assert h1 == h2
        assert len(h1) == 64

    def test_hash_changes_with_status(self):
        from datetime import datetime
        from app.services.audit_runner import _compute_report_hash
        ts = datetime(2026, 3, 26, 12, 0, 0)
        h1 = _compute_report_hash("all", "passed", "{}", ts)
        h2 = _compute_report_hash("all", "failed", "{}", ts)
        assert h1 != h2


# ===================================================================
# 4. SERVICE TESTS — Audit Runner
# ===================================================================


class TestAuditRunner:
    """Tests for the AuditRunner orchestration service."""

    def test_execute_all_scopes(self):
        db = TestingSessionLocal()
        from app.services.audit_runner import AuditRunner
        runner = AuditRunner(db)
        report = runner.execute(scope="all", triggered_by="manual")

        assert report.id is not None
        assert report.status in ("passed", "warnings", "error")
        assert report.scope == "all"
        assert report.triggered_by == "manual"
        assert report.duration_seconds >= 0
        assert report.integrity_hash is not None
        assert len(report.integrity_hash) == 64

        # Details should be valid JSON
        details = json.loads(report.details_json)
        assert "integrity" in details
        assert "retention" in details
        assert "coverage" in details
        assert "rule_health" in details
        assert "performance" in details
        db.close()

    def test_execute_single_scope(self):
        db = TestingSessionLocal()
        from app.services.audit_runner import AuditRunner
        runner = AuditRunner(db)
        report = runner.execute(scope="integrity")

        details = json.loads(report.details_json)
        assert "integrity" in details
        assert "coverage" not in details
        db.close()

    def test_execute_with_policy_link(self):
        db = TestingSessionLocal()
        from app.models.audit_policy import AuditPolicy
        from app.services.audit_runner import AuditRunner

        policy = AuditPolicy(
            name="test_linked", cron_expression="0 3 * * *", scope="all", enabled=True,
        )
        db.add(policy)
        db.commit()
        db.refresh(policy)

        runner = AuditRunner(db)
        report = runner.execute(scope="all", policy_id=policy.id, triggered_by="schedule")

        assert report.policy_id == policy.id
        assert report.triggered_by == "schedule"

        # Policy last_run_at should be updated
        db.refresh(policy)
        assert policy.last_run_at is not None
        db.close()

    def test_integrity_check_result_shape(self):
        db = TestingSessionLocal()
        from app.services.audit_runner import AuditRunner
        runner = AuditRunner(db)
        report = runner.execute(scope="integrity")
        details = json.loads(report.details_json)
        integrity = details["integrity"]
        assert "total_checked" in integrity
        assert "valid" in integrity
        assert "invalid" in integrity
        assert "unprotected" in integrity
        db.close()

    def test_retention_check_result_shape(self):
        db = TestingSessionLocal()
        from app.services.audit_runner import AuditRunner
        runner = AuditRunner(db)
        report = runner.execute(scope="retention")
        details = json.loads(report.details_json)
        retention = details["retention"]
        assert "retention_days" in retention
        assert "rows_purged" in retention
        db.close()

    def test_coverage_with_seeded_rules(self):
        db = TestingSessionLocal()
        from app.models.rule import Rule
        from app.services.audit_runner import AuditRunner

        db.add(Rule(
            name="cov_rule_1", description="test", group="g",
            priority=1, enabled=True,
            condition_dsl={"type": "condition", "field": "x", "op": ">", "value": 1},
            action="approve", created_by=1,
        ))
        db.add(Rule(
            name="cov_rule_2", description="test", group="g",
            priority=2, enabled=False,
            condition_dsl={"type": "condition", "field": "y", "op": "==", "value": "a"},
            action="reject", created_by=1,
        ))
        db.commit()

        runner = AuditRunner(db)
        report = runner.execute(scope="coverage")
        details = json.loads(report.details_json)
        cov = details["coverage"]
        assert cov["total_rules"] == 2
        assert cov["enabled_rules"] == 1
        assert cov["disabled_rules"] == 1
        db.close()

    def test_rule_health_detects_issues(self):
        db = TestingSessionLocal()
        from app.models.rule import Rule
        from app.services.audit_runner import AuditRunner

        # Rule with no description
        db.add(Rule(
            name="no_desc", description=None, group="g",
            priority=1, enabled=True,
            condition_dsl={"type": "condition", "field": "x", "op": ">", "value": 1},
            action="approve", created_by=1,
        ))
        # Disabled rule
        db.add(Rule(
            name="disabled", description="ok", group="g",
            priority=2, enabled=False,
            condition_dsl={"type": "condition", "field": "y", "op": "==", "value": "a"},
            action="reject", created_by=1,
        ))
        db.commit()

        runner = AuditRunner(db)
        report = runner.execute(scope="rule_health")
        assert report.status == "warnings"
        details = json.loads(report.details_json)
        health = details["rule_health"]
        assert health["disabled_count"] >= 1
        assert len(health["issues"]) >= 1
        db.close()

    def test_performance_check_returns_timings(self):
        db = TestingSessionLocal()
        from app.services.audit_runner import AuditRunner
        runner = AuditRunner(db)
        report = runner.execute(scope="performance")
        details = json.loads(report.details_json)
        perf = details["performance"]
        assert "audit_log_count" in perf
        assert "audit_count_query_ms" in perf
        assert "rule_count" in perf
        assert "integrity_check_50_rows_ms" in perf
        db.close()


# ===================================================================
# 5. API TESTS — Audit Policy CRUD
# ===================================================================


class TestAuditPolicyCRUD:
    """E2E tests for audit-policy CRUD endpoints."""

    def test_create_policy(self):
        name = _unique()
        resp = client.post("/api/v1/admin/audit-policy", json={
            "name": name,
            "description": "Daily integrity + coverage",
            "cron_expression": "0 2 * * *",
            "scope": "integrity,coverage",
            "enabled": True,
        })
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["name"] == name
        assert data["scope"] == "integrity,coverage"
        assert data["enabled"] is True
        assert data["next_run_at"] is not None
        assert data["id"] > 0

    def test_create_duplicate_name_rejected(self):
        name = _unique()
        resp1 = client.post("/api/v1/admin/audit-policy", json={
            "name": name, "scope": "all",
        })
        assert resp1.status_code == 200
        resp2 = client.post("/api/v1/admin/audit-policy", json={
            "name": name, "scope": "all",
        })
        assert resp2.status_code == 409

    def test_list_policies(self):
        name = _unique()
        client.post("/api/v1/admin/audit-policy", json={"name": name, "scope": "all"})
        resp = client.get("/api/v1/admin/audit-policy")
        assert resp.status_code == 200
        policies = resp.json()
        assert any(p["name"] == name for p in policies)

    def test_list_enabled_only(self):
        name_en = _unique("enabled")
        name_dis = _unique("disabled")
        client.post("/api/v1/admin/audit-policy", json={
            "name": name_en, "scope": "all", "enabled": True,
        })
        client.post("/api/v1/admin/audit-policy", json={
            "name": name_dis, "scope": "all", "enabled": False,
        })
        resp = client.get("/api/v1/admin/audit-policy?enabled_only=true")
        assert resp.status_code == 200
        names = {p["name"] for p in resp.json()}
        assert name_en in names
        assert name_dis not in names

    def test_get_policy_by_id(self):
        name = _unique()
        create = client.post("/api/v1/admin/audit-policy", json={
            "name": name, "scope": "all",
        })
        pid = create.json()["id"]
        resp = client.get(f"/api/v1/admin/audit-policy/{pid}")
        assert resp.status_code == 200
        assert resp.json()["id"] == pid

    def test_get_nonexistent_policy_404(self):
        resp = client.get("/api/v1/admin/audit-policy/99999")
        assert resp.status_code == 404

    def test_update_policy(self):
        name = _unique()
        create = client.post("/api/v1/admin/audit-policy", json={
            "name": name, "scope": "all", "cron_expression": "0 2 * * *",
        })
        pid = create.json()["id"]
        resp = client.patch(f"/api/v1/admin/audit-policy/{pid}", json={
            "cron_expression": "0 3 * * *",
            "enabled": False,
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["cron_expression"] == "0 3 * * *"
        assert data["enabled"] is False

    def test_delete_policy(self):
        name = _unique()
        create = client.post("/api/v1/admin/audit-policy", json={
            "name": name, "scope": "all",
        })
        pid = create.json()["id"]
        resp = client.delete(f"/api/v1/admin/audit-policy/{pid}")
        assert resp.status_code == 200
        # Verify deleted
        get_resp = client.get(f"/api/v1/admin/audit-policy/{pid}")
        assert get_resp.status_code == 404

    def test_delete_nonexistent_policy_404(self):
        resp = client.delete("/api/v1/admin/audit-policy/99999")
        assert resp.status_code == 404


# ===================================================================
# 6. API TESTS — Manual Audit Run
# ===================================================================


class TestManualAuditRun:
    """E2E tests for the manual audit-run trigger endpoint."""

    def test_trigger_full_audit(self):
        resp = client.post("/api/v1/admin/audit-run", json={"scope": "all"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["report_id"] > 0
        assert data["status"] in ("passed", "warnings", "error")
        assert "checks executed" in data["summary"]
        assert isinstance(data["details"], dict)

    def test_trigger_specific_scope(self):
        resp = client.post("/api/v1/admin/audit-run", json={
            "scope": "integrity,retention",
        })
        assert resp.status_code == 200
        details = resp.json()["details"]
        assert "integrity" in details
        assert "retention" in details
        assert "coverage" not in details

    def test_trigger_linked_to_policy(self):
        name = _unique()
        create = client.post("/api/v1/admin/audit-policy", json={
            "name": name, "scope": "integrity",
        })
        pid = create.json()["id"]
        resp = client.post("/api/v1/admin/audit-run", json={
            "scope": "integrity",
            "policy_id": pid,
        })
        assert resp.status_code == 200
        report_id = resp.json()["report_id"]

        # Verify report is linked
        report_resp = client.get(f"/api/v1/admin/audit-report/{report_id}")
        assert report_resp.status_code == 200
        assert report_resp.json()["policy_id"] == pid


# ===================================================================
# 7. API TESTS — Audit Reports
# ===================================================================


class TestAuditReports:
    """E2E tests for audit-report endpoints."""

    def test_list_reports_empty(self):
        resp = client.get("/api/v1/admin/audit-report")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_list_reports_after_run(self):
        client.post("/api/v1/admin/audit-run", json={"scope": "all"})
        resp = client.get("/api/v1/admin/audit-report")
        assert resp.status_code == 200
        reports = resp.json()
        assert len(reports) >= 1
        assert reports[0]["scope"] == "all"

    def test_filter_by_status(self):
        client.post("/api/v1/admin/audit-run", json={"scope": "integrity"})
        resp = client.get("/api/v1/admin/audit-report?status=passed")
        assert resp.status_code == 200

    def test_get_report_detail_has_json(self):
        run = client.post("/api/v1/admin/audit-run", json={"scope": "all"})
        rid = run.json()["report_id"]
        resp = client.get(f"/api/v1/admin/audit-report/{rid}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["details_json"] is not None
        assert data["integrity_hash"] is not None
        assert len(data["integrity_hash"]) == 64

    def test_nonexistent_report_404(self):
        resp = client.get("/api/v1/admin/audit-report/99999")
        assert resp.status_code == 404


# ===================================================================
# 8. BACKWARD COMPATIBILITY — Existing admin endpoints still work
# ===================================================================


class TestBackwardCompatibility:
    """Ensure existing admin endpoints are unaffected."""

    def test_existing_audit_integrity_endpoint(self):
        resp = client.get("/api/v1/admin/audit/integrity")
        assert resp.status_code == 200
        data = resp.json()
        assert "total_checked" in data

    def test_existing_audit_retention_endpoint(self):
        resp = client.post("/api/v1/admin/audit/retention")
        assert resp.status_code == 200
        data = resp.json()
        assert "retention_days" in data

    def test_existing_schema_endpoint(self):
        """Schema endpoint may fail in test (no alembic stamp) — that's OK."""
        resp = client.get("/api/v1/admin/schema")
        assert resp.status_code == 200

    def test_existing_db_health_endpoint(self):
        resp = client.get("/api/v1/admin/db/health")
        assert resp.status_code == 200

    def test_health_endpoint(self):
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "healthy"


# ===================================================================
# 9. SCHEDULER LIFECYCLE TESTS
# ===================================================================


class TestSchedulerLifecycle:
    """Tests for the background scheduler start/stop."""

    def test_start_stop_when_disabled(self):
        """Scheduler should be a no-op when AUDIT_SCHEDULER_ENABLED=false."""
        from app.services.audit_scheduler import (
            start_audit_scheduler,
            stop_audit_scheduler,
            _scheduler_thread,
        )
        # Default is disabled
        start_audit_scheduler()
        from app.services import audit_scheduler as sched_mod
        assert sched_mod._scheduler_thread is None
        stop_audit_scheduler()

    def test_start_stop_when_enabled(self):
        """Scheduler should start and stop cleanly when enabled."""
        from app.services import audit_scheduler as sched_mod
        from app.config import settings

        original = settings.AUDIT_SCHEDULER_ENABLED
        try:
            settings.AUDIT_SCHEDULER_ENABLED = True
            sched_mod.start_audit_scheduler()
            assert sched_mod._scheduler_thread is not None
            assert sched_mod._scheduler_thread.is_alive()
            sched_mod.stop_audit_scheduler()
            assert sched_mod._scheduler_thread is None
        finally:
            settings.AUDIT_SCHEDULER_ENABLED = original


# ===================================================================
# 10. PERFORMANCE BENCHMARKS
# ===================================================================


class TestAuditPerformance:
    """Performance benchmarks for audit operations."""

    def test_full_audit_completes_under_5_seconds(self):
        """A full-audit run on an empty DB should be fast."""
        db = TestingSessionLocal()
        from app.services.audit_runner import AuditRunner
        runner = AuditRunner(db)

        start = time.monotonic()
        report = runner.execute(scope="all")
        elapsed = time.monotonic() - start

        assert elapsed < 5.0, f"Full audit took {elapsed:.2f}s — expected < 5s"
        assert report.duration_seconds < 5.0
        db.close()

    def test_policy_crud_latency(self):
        """CRUD operations should be low-latency."""
        start = time.monotonic()

        name = _unique("perf")
        resp = client.post("/api/v1/admin/audit-policy", json={
            "name": name, "scope": "all",
        })
        pid = resp.json()["id"]

        client.get(f"/api/v1/admin/audit-policy/{pid}")
        client.patch(f"/api/v1/admin/audit-policy/{pid}", json={"enabled": False})
        client.delete(f"/api/v1/admin/audit-policy/{pid}")

        elapsed = time.monotonic() - start
        assert elapsed < 2.0, f"CRUD cycle took {elapsed:.2f}s — expected < 2s"

    def test_audit_run_with_rules(self):
        """Audit with seeded rules should still be fast."""
        db = TestingSessionLocal()
        from app.models.rule import Rule
        from app.services.audit_runner import AuditRunner

        # Seed 50 rules
        for i in range(50):
            db.add(Rule(
                name=f"perf_rule_{i}",
                description=f"rule {i}",
                group="perf_group",
                priority=i,
                enabled=True,
                condition_dsl={"type": "condition", "field": "x", "op": ">", "value": i},
                action="approve",
                created_by=1,
            ))
        db.commit()

        runner = AuditRunner(db)
        start = time.monotonic()
        report = runner.execute(scope="all")
        elapsed = time.monotonic() - start

        assert elapsed < 5.0, f"Audit with 50 rules took {elapsed:.2f}s"
        details = json.loads(report.details_json)
        assert details["coverage"]["total_rules"] == 50
        assert details["rule_health"]["total_rules"] == 50
        db.close()

    def test_report_listing_performance(self):
        """Listing many reports should be fast."""
        # Generate 20 reports
        for _ in range(20):
            client.post("/api/v1/admin/audit-run", json={"scope": "integrity"})

        start = time.monotonic()
        resp = client.get("/api/v1/admin/audit-report?limit=50")
        elapsed = time.monotonic() - start

        assert resp.status_code == 200
        assert elapsed < 2.0
        assert len(resp.json()) == 20


# ===================================================================
# 11. E2E INTEGRATION FLOW
# ===================================================================


class TestE2EAuditFlow:
    """Full end-to-end integration test."""

    def test_complete_audit_lifecycle(self):
        """Create policy → trigger run → verify report → list → delete."""
        # 1. Create policy
        name = _unique("e2e")
        create_resp = client.post("/api/v1/admin/audit-policy", json={
            "name": name,
            "description": "E2E test policy",
            "cron_expression": "0 4 * * *",
            "scope": "all",
            "enabled": True,
        })
        assert create_resp.status_code == 200
        policy = create_resp.json()
        pid = policy["id"]

        # 2. Trigger manual run linked to policy
        run_resp = client.post("/api/v1/admin/audit-run", json={
            "scope": "all",
            "policy_id": pid,
        })
        assert run_resp.status_code == 200
        run_data = run_resp.json()
        report_id = run_data["report_id"]
        assert run_data["status"] in ("passed", "warnings")

        # 3. Verify report details
        report_resp = client.get(f"/api/v1/admin/audit-report/{report_id}")
        assert report_resp.status_code == 200
        report = report_resp.json()
        assert report["policy_id"] == pid
        assert report["triggered_by"] == "manual"
        assert report["integrity_hash"] is not None

        # 4. Verify policy last_run_at was updated
        policy_resp = client.get(f"/api/v1/admin/audit-policy/{pid}")
        assert policy_resp.status_code == 200
        assert policy_resp.json()["last_run_at"] is not None

        # 5. List reports filtered by policy
        list_resp = client.get(f"/api/v1/admin/audit-report?policy_id={pid}")
        assert list_resp.status_code == 200
        assert len(list_resp.json()) >= 1

        # 6. Delete policy
        del_resp = client.delete(f"/api/v1/admin/audit-policy/{pid}")
        assert del_resp.status_code == 200

        # 7. Verify deletion
        get_resp = client.get(f"/api/v1/admin/audit-policy/{pid}")
        assert get_resp.status_code == 404

    def test_audit_creates_meta_audit_trail(self):
        """Running an audit should itself be logged in the audit trail."""
        from app.models.audit import AuditLog

        db = TestingSessionLocal()
        before_count = db.query(AuditLog).filter(
            AuditLog.action_type == "audit_run"
        ).count()

        client.post("/api/v1/admin/audit-run", json={"scope": "all"})

        after_count = db.query(AuditLog).filter(
            AuditLog.action_type == "audit_run"
        ).count()
        assert after_count > before_count
        db.close()
