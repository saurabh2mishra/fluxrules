"""FluxRules FastAPI application factory.

Creates and configures the FastAPI application, registering all
available routers. Optional routers that depend on extras (database,
auth, etc.) are loaded safely so that a minimal installation still works.
"""

from __future__ import annotations

import importlib
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from fluxrules.api.handlers import register_exception_handlers
from fluxrules.api.routes.health import router as health_router
from fluxrules.api.routes.validate import router as validate_router
from fluxrules.version import __version__

logger = logging.getLogger(__name__)


@asynccontextmanager
async def _lifespan(app: FastAPI):
    """Configure shared services at startup.

    Wires the Prometheus metrics collector into the core engine so that
    the PhreakEngine records real data
    instead of the default no-op NullMetrics.
    """
    from fluxrules.api.utils.metrics import PrometheusMetricsCollector
    from fluxrules.utils.metrics import set_metrics

    set_metrics(PrometheusMetricsCollector(engine="fluxrules"))
    logger.info("Prometheus metrics collector registered.")
    yield


def _load_optional_router(
    app: FastAPI,
    module_path: str,
    router_attr: str = "router",
    prefix: str | None = "/api/v1",
) -> None:
    """Safely import and register an optional FastAPI router.

    Args:
        app: The FastAPI application instance.
        module_path: Dotted import path (e.g. ``fluxrules.api.routes.rules``).
        router_attr: Attribute name holding the router in the module.
        prefix: URL prefix; ``None`` means no prefix.
    """
    short_name = module_path.rsplit(".", 1)[-1]
    try:
        module = importlib.import_module(module_path)
        router = getattr(module, router_attr)
        if prefix:
            app.include_router(router, prefix=prefix)
        else:
            app.include_router(router)
        logger.info("Loaded router: %s", short_name)
    except (ImportError, AttributeError):
        logger.debug("Optional router not available: %s", short_name)
    except Exception:
        logger.warning("Error loading optional router: %s", short_name, exc_info=True)


# Optional routers: (module_path, prefix or None)
_OPTIONAL_ROUTERS: list[tuple[str, str | None]] = [
    ("fluxrules.api.routes.evaluation", "/api/v1"),
    ("fluxrules.api.routes.rules", "/api/v1"),
    ("fluxrules.api.routes.rulesets", "/api/v1"),
    ("fluxrules.api.routes.audit", "/api/v1"),
    ("fluxrules.api.routes.events", "/api/v1"),
    ("fluxrules.api.routes.sessions", "/api/v1"),
    ("fluxrules.api.routes.metrics", "/api/v1"),
    ("fluxrules.api.routes.auth", "/api/v1"),
    ("fluxrules.api.routes.admin", "/api/v1"),
    ("fluxrules.api.routes.analytics", "/api/v1"),
    ("fluxrules.api.routes.audit_policy", "/api/v1"),
    ("fluxrules.api.routes.dependency_graph", "/api/v1"),
    ("fluxrules.api.routes.brms_analyze", "/api/v1"),
    ("fluxrules.api.routes.engines", None),
    ("fluxrules.api.routes.sdk", None),
]


def create_app() -> FastAPI:
    """Create and configure the FluxRules FastAPI application.

    Returns:
        A fully configured ``FastAPI`` instance.
    """
    app = FastAPI(title="fluxrules", version=__version__, lifespan=_lifespan)

    # Register custom exception handlers
    register_exception_handlers(app)

    # Core routers (always available)
    app.include_router(health_router)
    app.include_router(validate_router)

    # Database-backed / optional routers
    for module_path, prefix in _OPTIONAL_ROUTERS:
        _load_optional_router(app, module_path, prefix=prefix)

    return app
