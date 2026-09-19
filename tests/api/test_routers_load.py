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
    paths = {getattr(route, "path", "") for route in app.routes}
    # The router declares prefix="/brms" and is mounted under "/api/v1".
    brms_paths = {path for path in paths if "/brms" in path}

    assert brms_paths, f"no /brms routes registered; found {len(paths)} routes total"


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
