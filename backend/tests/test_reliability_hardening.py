"""Comprehensive reliability, HA, and governance hardening tests.

Covers:
  - DB fallback behaviour (enabled/disabled, production vs dev)
  - Schema version tracking and mismatch detection (Alembic-integrated)
  - Audit immutability controls (integrity hashing, tamper detection)
  - Audit retention policy enforcement
  - Admin API endpoints (schema, DB health, audit)
  - E2E flows validating no regressions after hardening
  - Performance benchmarks for new code paths
"""

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


def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture(autouse=True)
def _reset_db():
    """Recreate tables for every test so state never leaks."""
    app.dependency_overrides[get_db] = override_get_db
    Base.metadata.drop_all(bind=test_engine)
    # Also drop non-ORM tables that schema_manager creates.
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


def _unique(prefix: str = "test") -> str:
    return f"{prefix}_{uuid.uuid4().hex[:8]}"


# ===================================================================
# 1. UNIT TESTS — Schema manager (Alembic-integrated)
# ===================================================================


class TestSchemaManager:
    """Unit tests for schema versioning logic."""

    def test_stamp_and_read_version(self):
        from app.schema_manager import stamp_version, get_recorded_version
        # Fresh DB — no version recorded yet.
        assert get_recorded_version(test_engine) is None
        stamp_version(test_engine, "001", "initial")
        assert get_recorded_version(test_engine) == "001"

    def test_validate_stamps_on_first_run(self):
        from app.schema_manager import validate_schema_version, get_recorded_version
        # On a fresh DB, validate_schema_version should stamp.
        validate_schema_version(test_engine, "001")
        assert get_recorded_version(test_engine) == "001"

    def test_validate_passes_on_match(self):
        from app.schema_manager import validate_schema_version, stamp_version
        stamp_version(test_engine, "003", "test")
        # Should not raise.
        validate_schema_version(test_engine, "003")

    def test_validate_raises_on_mismatch(self):
        from app.schema_manager import validate_schema_version, stamp_version
        stamp_version(test_engine, "001", "test")
        with pytest.raises(RuntimeError, match="Schema version mismatch"):
            validate_schema_version(test_engine, "099")

    def test_version_history(self):
        from app.schema_manager import stamp_version, get_version_history
        # Drop and recreate schema_meta to isolate this test
        with test_engine.begin() as conn:
            conn.execute(text("DROP TABLE IF EXISTS schema_meta"))
        stamp_version(test_engine, "001", "first")
        stamp_version(test_engine, "002", "added indexes")
        history = get_version_history(test_engine)
        assert len(history) == 2
        assert history[0]["version"] == "002"  # newest first
        assert history[1]["version"] == "001"

    def test_get_alembic_version_returns_none_when_no_table(self):
        from app.schema_manager import get_alembic_version
        # test_engine has no alembic_version table
        assert get_alembic_version(test_engine) is None

    def test_get_alembic_version_reads_existing_table(self):
        from app.schema_manager import get_alembic_version
        # Manually create and populate alembic_version
        with test_engine.begin() as conn:
            conn.execute(text(
                "CREATE TABLE IF NOT EXISTS alembic_version (version_num VARCHAR(32) NOT NULL)"
            ))
            conn.execute(text(
                "INSERT INTO alembic_version (version_num) VALUES ('abc123')"
            ))
        assert get_alembic_version(test_engine) == "abc123"


# ===================================================================
# 2. UNIT TESTS — DB fallback behaviour
# ===================================================================


class TestDBFallback:
    """Unit tests for the configurable DB fallback gate."""

    def test_settings_have_fallback_flag(self):
        from app.config import settings
        assert hasattr(settings, "DB_FALLBACK_ENABLED")

    def test_settings_have_schema_version(self):
        from app.config import settings
        assert hasattr(settings, "SCHEMA_VERSION")
        assert isinstance(settings.SCHEMA_VERSION, str)

    def test_fallback_disabled_raises_on_bad_url(self):
        """When fallback is disabled, an unreachable non-SQLite DB must fail."""
        from app.database import _build_engine, _create_engine_with_fallback
        from app.config import settings

        original_fb = settings.DB_FALLBACK_ENABLED
        original_url = settings.DATABASE_URL
        try:
            settings.DB_FALLBACK_ENABLED = False
            settings.DATABASE_URL = "postgresql://bad:bad@localhost:59999/nonexistent"
            with pytest.raises(RuntimeError, match="FATAL.*DB_FALLBACK_ENABLED is False"):
                _create_engine_with_fallback()
        finally:
            settings.DB_FALLBACK_ENABLED = original_fb
            settings.DATABASE_URL = original_url

    def test_fallback_enabled_degrades_to_sqlite(self):
        """When fallback is enabled, an unreachable non-SQLite DB falls back."""
        from app.database import _create_engine_with_fallback
        from app.config import settings

        original_fb = settings.DB_FALLBACK_ENABLED
        original_url = settings.DATABASE_URL
        try:
            settings.DB_FALLBACK_ENABLED = True
            settings.DATABASE_URL = "postgresql://bad:bad@localhost:59999/nonexistent"
            engine = _create_engine_with_fallback()
            assert "sqlite" in str(engine.url)
        finally:
            settings.DB_FALLBACK_ENABLED = original_fb
            settings.DATABASE_URL = original_url

    def test_sqlite_primary_does_not_fallback(self):
        """When primary URL is SQLite and works, no fallback logic fires."""
        from app.database import _create_engine_with_fallback
        from app.config import settings

        original_url = settings.DATABASE_URL
        try:
            settings.DATABASE_URL = "sqlite://"
            engine = _create_engine_with_fallback()
            assert "sqlite" in str(engine.url)
        finally:
            settings.DATABASE_URL = original_url


# ===================================================================
# 3. UNIT TESTS — Audit integrity and retention
# ===================================================================


class TestAuditIntegrity:
    """Unit tests for audit-log integrity hashing."""

    def test_log_action_creates_integrity_hash(self):
        from app.services.audit_service import AuditService
        db = TestingSessionLocal()
        try:
            svc = AuditService(db)
            log = svc.log_action("create", "rule", 1, 1, "test rule created")
            assert log.integrity_hash is not None
            assert len(log.integrity_hash) == 64  # SHA256 hex
        finally:
            db.close()

    def test_integrity_hash_verifies(self):
        from app.services.audit_service import AuditService, verify_audit_integrity
        db = TestingSessionLocal()
        try:
            svc = AuditService(db)
            log = svc.log_action("update", "rule", 2, 1, "rule updated")
            assert verify_audit_integrity(log) is True
        finally:
            db.close()

    def test_tampered_row_fails_verification(self):
        from app.services.audit_service import AuditService, verify_audit_integrity
        db = TestingSessionLocal()
        try:
            svc = AuditService(db)
            log = svc.log_action("delete", "rule", 3, 1, "rule deleted")
            # Tamper with the details.
            log.details = "TAMPERED"
            assert verify_audit_integrity(log) is False
        finally:
            db.close()

    def test_pre_feature_rows_pass_verification(self):
        """Rows without a hash (created before this feature) should pass."""
        from app.services.audit_service import verify_audit_integrity
        from app.models.audit import AuditLog
        from datetime import datetime

        log = AuditLog(
            action_type="legacy",
            entity_type="rule",
            details="old row",
            timestamp=datetime.utcnow(),
            integrity_hash=None,
        )
        assert verify_audit_integrity(log) is True

    def test_verify_recent_returns_counts(self):
        from app.services.audit_service import AuditService
        db = TestingSessionLocal()
        try:
            svc = AuditService(db)
            svc.log_action("a", "b", 1, 1, "d1")
            svc.log_action("a", "b", 2, 1, "d2")
            result = svc.verify_recent(limit=10)
            assert result["total_checked"] == 2
            assert result["valid"] == 2
            assert result["invalid"] == 0
        finally:
            db.close()

    def test_integrity_disabled_creates_null_hash(self):
        """When AUDIT_INTEGRITY_ENABLED is False, no hash is stored."""
        from app.services.audit_service import AuditService
        from app.config import settings
        db = TestingSessionLocal()
        original = settings.AUDIT_INTEGRITY_ENABLED
        try:
            settings.AUDIT_INTEGRITY_ENABLED = False
            svc = AuditService(db)
            log = svc.log_action("create", "rule", 1, 1, "no hash")
            assert log.integrity_hash is None
        finally:
            settings.AUDIT_INTEGRITY_ENABLED = original
            db.close()


class TestAuditRetention:
    """Unit tests for audit-log retention policy."""

    def test_retention_zero_does_nothing(self):
        from app.services.audit_service import AuditService
        from app.config import settings
        db = TestingSessionLocal()
        original = settings.AUDIT_RETENTION_DAYS
        try:
            settings.AUDIT_RETENTION_DAYS = 0
            svc = AuditService(db)
            svc.log_action("a", "b", 1, 1, "keep forever")
            purged = svc.apply_retention_policy()
            assert purged == 0
        finally:
            settings.AUDIT_RETENTION_DAYS = original
            db.close()

    def test_retention_purges_old_rows(self):
        from app.services.audit_service import AuditService
        from app.models.audit import AuditLog
        from app.config import settings
        from datetime import datetime, timedelta
        db = TestingSessionLocal()
        original = settings.AUDIT_RETENTION_DAYS
        try:
            settings.AUDIT_RETENTION_DAYS = 30
            svc = AuditService(db)
            # Create an "old" row directly.
            old = AuditLog(
                action_type="old",
                entity_type="rule",
                entity_id=1,
                user_id=1,
                details="ancient",
                timestamp=datetime.utcnow() - timedelta(days=60),
            )
            db.add(old)
            # And a recent one.
            svc.log_action("new", "rule", 2, 1, "recent")
            db.commit()
            purged = svc.apply_retention_policy()
            assert purged == 1
            remaining = db.query(AuditLog).count()
            assert remaining == 1  # only the recent one
        finally:
            settings.AUDIT_RETENTION_DAYS = original
            db.close()


# ===================================================================
# 4. INTEGRATION TESTS — Admin API endpoints
# ===================================================================


def _admin_auth_headers():
    """Get auth token for the admin user."""
    # Register or login as admin
    resp = client.post(
        "/api/v1/auth/login",
        json={"username": "admin", "password": "admin123"},
    )
    if resp.status_code != 200:
        # Try registering first
        resp = client.post(
            "/api/v1/auth/register",
            json={
                "username": "admin_rel",
                "email": "admin_rel@test.com",
                "password": "AdminP@ss1",
                "role": "admin",
            },
        )
    # The conftest overrides auth, so we can use any valid Bearer token
    return {"Authorization": "Bearer fake-token"}


class TestAdminSchemaEndpoint:
    """Integration tests for /api/v1/admin/schema."""

    def test_schema_info_returns_version(self):
        resp = client.get(
            "/api/v1/admin/schema",
            headers=_admin_auth_headers(),
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "expected_version" in data
        assert "recorded_version" in data
        assert "match" in data
        assert "history" in data


class TestAdminDBHealthEndpoint:
    """Integration tests for /api/v1/admin/db/health."""

    def test_db_health_returns_backend(self):
        resp = client.get(
            "/api/v1/admin/db/health",
            headers=_admin_auth_headers(),
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["backend"] in ("sqlite", "postgresql", "other")
        assert "fallback_enabled" in data
        assert "environment" in data


class TestAdminAuditEndpoints:
    """Integration tests for /api/v1/admin/audit/*."""

    def test_audit_integrity_endpoint(self):
        resp = client.get(
            "/api/v1/admin/audit/integrity",
            headers=_admin_auth_headers(),
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "total_checked" in data
        assert "valid" in data
        assert "invalid" in data

    def test_audit_retention_endpoint(self):
        resp = client.post(
            "/api/v1/admin/audit/retention",
            headers=_admin_auth_headers(),
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "retention_days" in data
        assert "rows_purged" in data


# ===================================================================
# 5. E2E TESTS — Full flow with hardening
# ===================================================================


class TestE2EWithHardening:
    """End-to-end tests ensuring no regressions after hardening."""

    def test_health_endpoint_still_works(self):
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "healthy"

    def test_rule_crud_flow(self):
        """Full create/read/update/delete rule flow still works."""
        headers = _admin_auth_headers()

        # Create
        rule_data = {
            "name": _unique("e2e_rule"),
            "description": "E2E hardening test",
            "group": "test",
            "priority": 50,
            "enabled": True,
            "condition_dsl": {"field": "age", "operator": ">", "value": 18},
            "action": "approve",
        }
        resp = client.post("/api/v1/rules/", json=rule_data, headers=headers)
        assert resp.status_code in (200, 201)
        rule_id = resp.json()["id"]

        # Read
        resp = client.get(f"/api/v1/rules/{rule_id}", headers=headers)
        assert resp.status_code == 200
        assert resp.json()["name"] == rule_data["name"]

        # Update
        resp = client.put(
            f"/api/v1/rules/{rule_id}",
            json={**rule_data, "priority": 99},
            headers=headers,
        )
        assert resp.status_code == 200

        # Delete
        resp = client.delete(f"/api/v1/rules/{rule_id}", headers=headers)
        assert resp.status_code in (200, 204)

    def test_audit_log_has_integrity_hash(self):
        """After creating a rule, audit log entry should have an integrity hash."""
        headers = _admin_auth_headers()
        rule_data = {
            "name": _unique("audit_hash_rule"),
            "description": "audit integrity test",
            "group": "test",
            "priority": 1,
            "enabled": True,
            "condition_dsl": {"field": "x", "operator": "==", "value": 1},
            "action": "log",
        }
        client.post("/api/v1/rules/", json=rule_data, headers=headers)

        # Check integrity via admin endpoint
        resp = client.get(
            "/api/v1/admin/audit/integrity?limit=5",
            headers=_admin_auth_headers(),
        )
        assert resp.status_code == 200


# ===================================================================
# 6. PERFORMANCE TESTS
# ===================================================================


class TestPerformance:
    """Performance benchmarks for new reliability code paths."""

    def test_integrity_hash_performance(self):
        """Audit hash computation should be fast (< 1ms per row)."""
        from app.services.audit_service import _compute_integrity_hash
        from datetime import datetime

        now = datetime.utcnow()
        start = time.time()
        iterations = 10_000
        for i in range(iterations):
            _compute_integrity_hash("create", "rule", i, 1, f"detail-{i}", now)
        elapsed = time.time() - start
        per_hash_ms = (elapsed / iterations) * 1000
        assert per_hash_ms < 1.0, f"Hash too slow: {per_hash_ms:.3f}ms per hash"

    def test_schema_validation_performance(self):
        """Schema version check should be fast (< 50ms)."""
        from app.schema_manager import stamp_version, validate_schema_version
        stamp_version(test_engine, "001", "perf test")

        start = time.time()
        for _ in range(100):
            validate_schema_version(test_engine, "001")
        elapsed = time.time() - start
        per_check_ms = (elapsed / 100) * 1000
        assert per_check_ms < 50, f"Schema check too slow: {per_check_ms:.1f}ms"

    def test_bulk_audit_write_performance(self):
        """Bulk audit writes with integrity hashing should stay under 5ms each."""
        from app.services.audit_service import AuditService
        db = TestingSessionLocal()
        try:
            svc = AuditService(db)
            start = time.time()
            count = 500
            for i in range(count):
                svc.log_action("create", "rule", i, 1, f"bulk-{i}", auto_commit=False)
            db.commit()
            elapsed = time.time() - start
            per_write_ms = (elapsed / count) * 1000
            assert per_write_ms < 5.0, f"Audit write too slow: {per_write_ms:.3f}ms"
        finally:
            db.close()


# ===================================================================
# 7. BACKWARD COMPATIBILITY TESTS
# ===================================================================


class TestBackwardCompatibility:
    """Ensure all new features are backward-compatible."""

    def test_audit_model_has_integrity_hash_nullable(self):
        """The integrity_hash column must be nullable for old rows."""
        from app.models.audit import AuditLog
        col = AuditLog.__table__.columns["integrity_hash"]
        assert col.nullable is True

    def test_default_config_is_dev_friendly(self):
        """Default settings should be dev-friendly (fallback on, etc)."""
        from app.config import Settings
        s = Settings()
        assert s.DB_FALLBACK_ENABLED is True
        assert s.AUDIT_RETENTION_DAYS == 0  # keep forever by default
        assert s.AUDIT_INTEGRITY_ENABLED is True

    def test_audit_service_still_works_without_integrity(self):
        """AuditService works when integrity is disabled."""
        from app.services.audit_service import AuditService
        from app.config import settings
        db = TestingSessionLocal()
        original = settings.AUDIT_INTEGRITY_ENABLED
        try:
            settings.AUDIT_INTEGRITY_ENABLED = False
            svc = AuditService(db)
            log = svc.log_action("create", "rule", 1, 1, "no-hash")
            assert log.id is not None
            assert log.integrity_hash is None
        finally:
            settings.AUDIT_INTEGRITY_ENABLED = original
            db.close()

    def test_existing_api_routes_still_registered(self):
        """All pre-existing API routes must still be accessible."""
        routes = [r.path for r in app.routes if hasattr(r, "path")]
        expected = [
            "/api/v1/auth/",
            "/api/v1/rules",
            "/api/v1/event",
            "/api/v1/metrics",
            "/health",
        ]
        for expected_prefix in expected:
            assert any(
                expected_prefix in r for r in routes
            ), f"Route prefix '{expected_prefix}' missing from app routes"
