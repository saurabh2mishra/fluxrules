"""Pytest configuration and shared fixtures for FluxRules tests.

Provides:
- FastAPI app and authentication fixtures for API tests
- Database setup and session fixtures
- Sample data fixtures (rules, events) for unit and integration tests
- Logging configuration cleanup between tests
"""

from __future__ import annotations

import logging
from collections.abc import Generator
from typing import Any

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

logger = logging.getLogger(__name__)

# in-memory SQLite for all API tests
SQLALCHEMY_DATABASE_URL = "sqlite://"

test_engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)


def _fake_get_current_user():
    """Create a fake test user for authentication."""

    class _User:
        id = 1
        username = "testuser"
        email = "testuser@example.com"
        role = "business"
        is_active = True

    return _User()


def _fake_get_current_admin():
    """Create a fake admin user for authentication."""

    class _User:
        id = 1
        username = "admin"
        email = "admin@example.com"
        role = "admin"
        is_active = True

    return _User()


# FastAPI and Authentication Fixtures


@pytest.fixture(scope="session")
def app():
    """Create the FastAPI application once per test session."""
    from fluxrules.api.app import create_app

    return create_app()


@pytest.fixture(scope="session", autouse=True)
def override_auth_dependency(app):
    """Override auth dependencies so tests don't need valid JWTs."""
    from fluxrules.api import deps

    app.dependency_overrides[deps.get_current_user] = _fake_get_current_user
    app.dependency_overrides[deps.get_current_admin] = _fake_get_current_admin
    yield
    app.dependency_overrides.pop(deps.get_current_user, None)
    app.dependency_overrides.pop(deps.get_current_admin, None)


@pytest.fixture()
def clean_db():
    """Drop and recreate all tables for each test that needs a fresh DB."""
    from fluxrules.api.database import Base

    Base.metadata.drop_all(bind=test_engine)
    Base.metadata.create_all(bind=test_engine)
    yield
    Base.metadata.drop_all(bind=test_engine)


@pytest.fixture()
def client(app, clean_db):
    """Return a TestClient wired to the in-memory DB."""
    from fastapi.testclient import TestClient

    from fluxrules.api.database import get_db

    def _override_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = _override_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.pop(get_db, None)


# Database and Session Fixtures


@pytest.fixture(scope="session")
def test_database_url() -> str:
    """Provide test database URL."""
    return "sqlite:///:memory:"


@pytest.fixture(scope="session")
def engine():
    """Create test database engine."""
    from sqlalchemy.orm import declarative_base

    database_url = "sqlite:///:memory:"
    engine = create_engine(database_url, connect_args={"check_same_thread": False})

    # Create all tables
    Base = declarative_base()
    Base.metadata.create_all(bind=engine)

    yield engine
    engine.dispose()


@pytest.fixture
def db_session(engine) -> Generator[Session, None, None]:
    """Provide a test database session."""
    connection = engine.connect()
    transaction = connection.begin()
    session = sessionmaker(autocommit=False, autoflush=False, bind=engine)()

    yield session

    session.close()
    transaction.rollback()
    connection.close()


# Sample Data Fixtures


@pytest.fixture
def sample_rules() -> list[dict[str, Any]]:
    """Provide sample rules for testing."""
    return [
        {
            "id": 1,
            "name": "high_transaction",
            "priority": 1,
            "action": "flag_for_review",
            "condition_dsl": {
                "type": "condition",
                "field": "amount",
                "op": ">",
                "value": 1000,
            },
        },
        {
            "id": 2,
            "name": "vip_status",
            "priority": 2,
            "action": "grant_access",
            "condition_dsl": {
                "type": "condition",
                "field": "status",
                "op": "==",
                "value": "vip",
            },
        },
        {
            "id": 3,
            "name": "combined_check",
            "priority": 3,
            "action": "notify_team",
            "condition_dsl": {
                "type": "group",
                "op": "AND",
                "children": [
                    {"type": "condition", "field": "amount", "op": ">", "value": 500},
                    {
                        "type": "condition",
                        "field": "status",
                        "op": "==",
                        "value": "active",
                    },
                ],
            },
        },
    ]


@pytest.fixture
def sample_event() -> dict[str, Any]:
    """Provide a sample event for testing."""
    return {
        "amount": 1500.0,
        "status": "vip",
        "account_id": "ACC123",
        "timestamp": "2024-01-01T12:00:00Z",
    }


@pytest.fixture
def sample_events() -> list[dict[str, Any]]:
    """Provide multiple sample events for testing."""
    return [
        {
            "amount": 1500.0,
            "status": "vip",
            "account_id": "ACC123",
        },
        {
            "amount": 300.0,
            "status": "active",
            "account_id": "ACC124",
        },
        {
            "amount": 5000.0,
            "status": "active",
            "account_id": "ACC125",
        },
        {
            "amount": 100.0,
            "status": "inactive",
            "account_id": "ACC126",
        },
    ]


@pytest.fixture
def rule_payload():
    """Return the :func:`build_rule_payload` builder for API rule payloads."""
    from tests.factories import build_rule_payload

    return build_rule_payload


# Logging and Cleanup Fixtures


@pytest.fixture(autouse=True)
def reset_logging():
    """Reset logging configuration between tests."""
    # Reset all fluxrules loggers to clean state
    for name in list(logging.Logger.manager.loggerDict):
        if name.startswith("fluxrules"):
            _lg = logging.getLogger(name)
            _lg.handlers.clear()
            _lg.setLevel(logging.NOTSET)
            _lg.propagate = True
    yield
    for name in list(logging.Logger.manager.loggerDict):
        if name.startswith("fluxrules"):
            _lg = logging.getLogger(name)
            _lg.handlers.clear()
            _lg.setLevel(logging.NOTSET)
            _lg.propagate = True
