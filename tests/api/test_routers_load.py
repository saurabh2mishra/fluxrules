"""Every API router must load.

The `brms_analyze` router crashed at import time for an unknown period and was
silently absent from every deployment: `app.py` catches router-load failures so
the app still starts. That graceful degradation is correct behaviour, but it
means a broken route is invisible unless something asserts otherwise.

This test is that something. It protects every route, not just `brms`.
"""

from __future__ import annotations

import logging

import pytest

fastapi = pytest.importorskip("fastapi")


def test_no_optional_router_fails_to_load(caplog) -> None:
    """App creation must not swallow any router-import failure."""
    from fluxrules.api.app import create_app

    with caplog.at_level(logging.WARNING, logger="fluxrules.api.app"):
        create_app()

    failures = [
        record.getMessage()
        for record in caplog.records
        if "Error loading optional router" in record.getMessage()
    ]
    assert not failures, "routers failed to load: " + "; ".join(failures)


def test_brms_routes_are_registered() -> None:
    """The previously-dead `/brms` routes must actually be mounted."""
    from fluxrules.api.app import create_app

    app = create_app()
    brms_paths = {path for path in app.openapi()["paths"] if "/brms" in path}

    assert brms_paths, "no /brms routes registered in the OpenAPI schema"


def test_public_route_contract_is_registered() -> None:
    """Public operations remain visible when framework routers are lazy."""
    from fluxrules.api.app import create_app

    paths = create_app().openapi()["paths"]
    expected_operations = {
        ("/health", "get"),
        ("/api/v1/evaluate", "post"),
        ("/api/v1/rules/validate", "post"),
        ("/api/v1/auth/token", "post"),
        ("/api/v1/brms/analyze", "post"),
        ("/api/v1/engines/evaluate", "post"),
    }

    registered_operations = {
        (path, method)
        for path, operations in paths.items()
        for method in operations
    }
    missing_operations = expected_operations - registered_operations

    assert not missing_operations, f"API operations not registered: {sorted(missing_operations)}"


def test_app_lifespan_starts() -> None:
    """The API's runtime-only lifespan dependencies are available."""
    from fastapi.testclient import TestClient

    from fluxrules.api.app import create_app

    with TestClient(create_app()) as client:
        response = client.get("/health")

    assert response.status_code == 200


def test_brms_router_module_imports_cleanly() -> None:
    """Direct import must not raise.

    Fails if the module-level `RuleService()` singleton is ever reintroduced.
    """
    import importlib

    module = importlib.import_module("fluxrules.api.routes.brms_analyze")
    assert not hasattr(module, "_rule_service"), (
        "`_rule_service` is back as a module-level singleton - it needs a "
        "per-request Session and will crash this router on import."
    )
