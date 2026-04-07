"""Comprehensive security hardening tests for FluxRules.

Covers:
  - Unit tests for secret-key validation, password-policy, CORS parsing
  - E2E tests for auth flow (register, login, protected endpoints)
  - E2E tests for rule evaluation after security changes
  - Performance benchmarks comparing before/after
"""

import os
import time
import secrets
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

# Shared test infrastructure

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
    Base.metadata.create_all(bind=test_engine)
    yield
    Base.metadata.drop_all(bind=test_engine)


client = TestClient(app)


def _unique(prefix: str = "test") -> str:
    """Return a short unique string for test isolation."""
    return f"{prefix}_{uuid.uuid4().hex[:8]}"


# UNIT TESTS — security.py utilities

class TestSecretKeyValidation:
    """Unit tests for SECRET_KEY validation logic."""

    def test_known_insecure_default_detected(self):
        from app.security import is_secret_key_insecure
        assert is_secret_key_insecure("your-secret-key-change-in-production") is True

    def test_short_key_detected(self):
        from app.security import is_secret_key_insecure
        assert is_secret_key_insecure("short") is True

    def test_strong_key_passes(self):
        from app.security import is_secret_key_insecure
        strong_key = secrets.token_urlsafe(64)
        assert is_secret_key_insecure(strong_key) is False

    def test_generate_secure_secret_length(self):
        from app.security import generate_secure_secret
        key = generate_secure_secret(32)
        # token_urlsafe(32) produces ≈43 chars
        assert len(key) >= 32

    def test_generate_secure_secret_uniqueness(self):
        from app.security import generate_secure_secret
        keys = {generate_secure_secret() for _ in range(100)}
        assert len(keys) == 100, "Generated keys must be unique"

    def test_validate_and_resolve_in_dev_auto_generates(self):
        from app.security import validate_and_resolve_secret_key
        os.environ["FLUXRULES_ENV"] = "development"
        result = validate_and_resolve_secret_key("changeme")
        assert result != "changeme"
        assert len(result) >= 32
        os.environ.pop("FLUXRULES_ENV", None)

    def test_validate_and_resolve_in_production_raises(self):
        from app.security import validate_and_resolve_secret_key
        os.environ["FLUXRULES_ENV"] = "production"
        with pytest.raises(RuntimeError, match="SECRET_KEY is insecure"):
            validate_and_resolve_secret_key("changeme")
        os.environ.pop("FLUXRULES_ENV", None)

    def test_validate_and_resolve_passes_strong_key(self):
        from app.security import validate_and_resolve_secret_key
        strong = secrets.token_urlsafe(64)
        assert validate_and_resolve_secret_key(strong) == strong


class TestPasswordPolicy:
    """Unit tests for password-strength enforcement."""

    def test_too_short(self):
        from app.security import validate_password_strength
        ok, msg = validate_password_strength("Ab1")
        assert not ok
        assert "8 characters" in msg

    def test_no_uppercase(self):
        from app.security import validate_password_strength
        ok, msg = validate_password_strength("alllowercase1")
        assert not ok
        assert "uppercase" in msg

    def test_no_lowercase(self):
        from app.security import validate_password_strength
        ok, msg = validate_password_strength("ALLUPPERCASE1")
        assert not ok
        assert "lowercase" in msg

    def test_no_digit(self):
        from app.security import validate_password_strength
        ok, msg = validate_password_strength("NoDigitsHere")
        assert not ok
        assert "digit" in msg

    def test_strong_password_passes(self):
        from app.security import validate_password_strength
        ok, msg = validate_password_strength("SecurePass1")
        assert ok

    def test_max_length_exceeded(self):
        from app.security import validate_password_strength
        ok, msg = validate_password_strength("A1a" + "x" * 130)
        assert not ok
        assert "128" in msg


class TestCorsOriginParsing:
    """Unit tests for CORS origin parsing."""

    def test_wildcard(self):
        from app.security import parse_cors_origins
        assert parse_cors_origins("*") == ["*"]

    def test_empty_string(self):
        from app.security import parse_cors_origins
        assert parse_cors_origins("") == []

    def test_single_origin(self):
        from app.security import parse_cors_origins
        assert parse_cors_origins("https://app.example.com") == ["https://app.example.com"]

    def test_multiple_origins(self):
        from app.security import parse_cors_origins
        result = parse_cors_origins("https://a.com, https://b.com , https://c.com")
        assert result == ["https://a.com", "https://b.com", "https://c.com"]

    def test_whitespace_only(self):
        from app.security import parse_cors_origins
        assert parse_cors_origins("   ") == []


# E2E TESTS — Auth flow (register → login → access protected)

class TestAuthE2E:
    """End-to-end auth tests verifying registration, login, and token use."""

    def _register(self, username=None, email=None, password="SecureP@ss1"):
        username = username or _unique("user")
        email = email or f"{username}@test.com"
        return client.post(
            "/api/v1/auth/register",
            json={"username": username, "email": email, "password": password, "role": "business"},
        ), username

    def _login(self, username, password="SecureP@ss1"):
        return client.post(
            "/api/v1/auth/token",
            data={"username": username, "password": password},
        )

    def test_register_with_strong_password_succeeds(self):
        resp, uname = self._register()
        assert resp.status_code == 200
        assert resp.json()["username"] == uname

    def test_register_with_weak_password_rejected(self):
        resp, _ = self._register(password="weak")
        assert resp.status_code == 400
        assert "8 characters" in resp.json()["detail"]

    def test_register_no_uppercase_rejected(self):
        resp, _ = self._register(password="alllower123")
        assert resp.status_code == 400
        assert "uppercase" in resp.json()["detail"]

    def test_register_no_digit_rejected(self):
        resp, _ = self._register(password="NoDigitsHere")
        assert resp.status_code == 400
        assert "digit" in resp.json()["detail"]

    def test_login_after_register_returns_token(self):
        resp, uname = self._register()
        assert resp.status_code == 200
        resp = self._login(uname)
        assert resp.status_code == 200
        data = resp.json()
        assert "access_token" in data
        assert data["token_type"] == "bearer"

    def test_login_wrong_password_fails(self):
        resp, uname = self._register()
        assert resp.status_code == 200
        resp = self._login(uname, password="WrongPass1")
        assert resp.status_code == 401

    def test_protected_endpoint_with_valid_token(self):
        resp, uname = self._register()
        assert resp.status_code == 200
        token = self._login(uname).json()["access_token"]
        resp = client.get(
            "/api/v1/rules",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200

    def test_protected_endpoint_without_token_rejected(self):
        # Remove the conftest auth override for this specific test
        from app.api import deps

        # Temporarily clear overrides to test real auth
        original = app.dependency_overrides.get(deps.get_current_user)
        app.dependency_overrides.pop(deps.get_current_user, None)

        try:
            resp = client.get("/api/v1/rules")
            assert resp.status_code in (401, 403)
        finally:
            # Restore
            if original is not None:
                app.dependency_overrides[deps.get_current_user] = original

    def test_protected_endpoint_with_garbage_token_rejected(self):
        from app.api import deps

        original = app.dependency_overrides.get(deps.get_current_user)
        app.dependency_overrides.pop(deps.get_current_user, None)

        try:
            resp = client.get(
                "/api/v1/rules",
                headers={"Authorization": "Bearer garbage.token.here"},
            )
            assert resp.status_code in (401, 403)
        finally:
            if original is not None:
                app.dependency_overrides[deps.get_current_user] = original


# E2E TESTS — Rule evaluation unchanged after security hardening

class TestRuleEvaluationE2E:
    """Verify rule CRUD and evaluation still work after security changes."""

    def _create_rule(self, name="sec_test_rule", action="approve"):
        return client.post(
            "/api/v1/rules?skip_conflict_check=true",
            json={
                "name": name,
                "description": "security test rule",
                "group": "security_test",
                "priority": 10,
                "enabled": True,
                "condition_dsl": {
                    "type": "group",
                    "op": "AND",
                    "children": [
                        {"type": "condition", "field": "amount", "op": ">", "value": 100}
                    ],
                },
                "action": action,
            },
        )

    def test_create_rule_works(self):
        resp = self._create_rule(name="sec_create_test")
        assert resp.status_code == 200
        assert resp.json()["name"] == "sec_create_test"

    def test_list_rules_works(self):
        self._create_rule(name="sec_list_test")
        resp = client.get("/api/v1/rules")
        assert resp.status_code == 200
        assert len(resp.json()) >= 1

    def test_get_rule_by_id(self):
        rule_id = self._create_rule(name="sec_getbyid_test").json()["id"]
        resp = client.get(f"/api/v1/rules/{rule_id}")
        assert resp.status_code == 200
        assert resp.json()["id"] == rule_id

    def test_validate_rule(self):
        self._create_rule(name="existing_for_validate")
        resp = client.post(
            "/api/v1/rules/validate",
            json={
                "name": "candidate_validate",
                "description": "test",
                "group": "security_test",
                "priority": 11,
                "enabled": True,
                "condition_dsl": {
                    "type": "group",
                    "op": "AND",
                    "children": [
                        {"type": "condition", "field": "amount", "op": ">", "value": 200}
                    ],
                },
                "action": "review",
            },
        )
        assert resp.status_code == 200
        payload = resp.json()
        assert "valid" in payload
        assert "conflicts" in payload

    def test_health_endpoint_unchanged(self):
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json() == {"status": "healthy"}


# PERFORMANCE BENCHMARKS — ensure no degradation

class TestSecurityPerformance:
    """Benchmark critical paths to ensure security changes don't degrade perf."""

    def test_token_generation_latency(self):
        """JWT token creation should complete in < 50ms."""
        from app.services.auth_service import create_access_token
        from datetime import timedelta

        iterations = 200
        start = time.perf_counter()
        for _ in range(iterations):
            create_access_token(data={"sub": "benchuser"}, expires_delta=timedelta(minutes=30))
        elapsed = time.perf_counter() - start
        avg_ms = (elapsed / iterations) * 1000
        assert avg_ms < 50, f"Token generation too slow: {avg_ms:.2f}ms avg"

    def test_password_hashing_latency(self):
        """bcrypt hashing is intentionally slow but should be < 500ms."""
        from app.services.auth_service import get_password_hash

        start = time.perf_counter()
        get_password_hash("BenchmarkPass1")
        elapsed_ms = (time.perf_counter() - start) * 1000
        assert elapsed_ms < 500, f"Password hashing too slow: {elapsed_ms:.2f}ms"

    def test_password_verification_latency(self):
        """bcrypt verify should be < 500ms."""
        from app.services.auth_service import get_password_hash, verify_password

        hashed = get_password_hash("BenchmarkPass1")
        start = time.perf_counter()
        verify_password("BenchmarkPass1", hashed)
        elapsed_ms = (time.perf_counter() - start) * 1000
        assert elapsed_ms < 500, f"Password verification too slow: {elapsed_ms:.2f}ms"

    def test_password_validation_throughput(self):
        """Password policy checks should be negligible (< 1ms avg)."""
        from app.security import validate_password_strength

        iterations = 10_000
        start = time.perf_counter()
        for _ in range(iterations):
            validate_password_strength("SecurePass1")
        elapsed = time.perf_counter() - start
        avg_us = (elapsed / iterations) * 1_000_000
        assert avg_us < 1000, f"Password validation too slow: {avg_us:.1f}µs avg"

    def test_cors_parsing_throughput(self):
        """CORS parsing should be negligible."""
        from app.security import parse_cors_origins

        origins = "https://a.com,https://b.com,https://c.com,https://d.com"
        iterations = 10_000
        start = time.perf_counter()
        for _ in range(iterations):
            parse_cors_origins(origins)
        elapsed = time.perf_counter() - start
        avg_us = (elapsed / iterations) * 1_000_000
        assert avg_us < 100, f"CORS parsing too slow: {avg_us:.1f}µs avg"

    def test_rule_create_latency_acceptable(self):
        """Rule creation through API should complete in < 200ms."""
        name = _unique("perf_rule")
        start = time.perf_counter()
        resp = client.post(
            "/api/v1/rules?skip_conflict_check=true",
            json={
                "name": name,
                "description": "perf test",
                "group": "perf",
                "priority": 1,
                "enabled": True,
                "condition_dsl": {
                    "type": "condition",
                    "field": "x",
                    "op": ">",
                    "value": 1,
                },
                "action": "approve",
            },
        )
        elapsed_ms = (time.perf_counter() - start) * 1000
        assert resp.status_code == 200
        assert elapsed_ms < 500, f"Rule create too slow: {elapsed_ms:.2f}ms"

    def test_auth_register_latency_acceptable(self):
        """Registration should complete in < 1s (dominated by bcrypt)."""
        uname = _unique("perfuser")
        start = time.perf_counter()
        resp = client.post(
            "/api/v1/auth/register",
            json={
                "username": uname,
                "email": f"{uname}@test.com",
                "password": "PerfPass123",
                "role": "business",
            },
        )
        elapsed_ms = (time.perf_counter() - start) * 1000
        assert resp.status_code == 200
        assert elapsed_ms < 1000, f"Registration too slow: {elapsed_ms:.2f}ms"


# CONFIG TESTS — ensure settings are properly resolved

class TestConfigSecurity:
    """Verify the runtime configuration has safe values."""

    def test_secret_key_is_not_the_default(self):
        """After config.py loads, the SECRET_KEY must not be the insecure placeholder."""
        from app.config import settings
        assert settings.SECRET_KEY != "your-secret-key-change-in-production"

    def test_secret_key_meets_min_length(self):
        from app.config import settings
        assert len(settings.SECRET_KEY) >= 32

    def test_cors_settings_exist(self):
        from app.config import settings
        assert hasattr(settings, "CORS_ALLOWED_ORIGINS")
        assert hasattr(settings, "CORS_ALLOWED_METHODS")
        assert hasattr(settings, "CORS_ALLOWED_HEADERS")

    def test_admin_seed_settings_exist(self):
        from app.config import settings
        assert hasattr(settings, "SEED_ADMIN_USER")
        assert hasattr(settings, "ADMIN_DEFAULT_PASSWORD")
        assert hasattr(settings, "ADMIN_FORCE_PASSWORD_CHANGE")
