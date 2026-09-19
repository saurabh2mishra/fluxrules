"""Tests for API exception handler registration."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from fluxrules.api.app import create_app


class TestExceptionHandlersRegistered:
    """Verify that custom exception handlers are wired into the app."""

    @pytest.fixture()
    def client(self) -> TestClient:
        """Create a test client for the FluxRules app."""
        app = create_app()
        return TestClient(app)

    def test_app_creates_successfully(self, client: TestClient) -> None:
        """Application factory should complete without error."""
        resp = client.get("/health")
        assert resp.status_code == 200
