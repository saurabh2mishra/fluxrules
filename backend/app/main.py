"""Application entrypoint for the FluxRules FastAPI service."""

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api.routes.analytics import router as analytics_router
from app.api.routes.admin import router as admin_router
from app.api.routes.audit_policy import router as audit_policy_router
from app.api.routes.auth import router as auth_router
from app.api.routes.dependency_graph import router as dependency_graph_router
from app.api.routes.events import router as events_router
from app.api.routes.metrics import router as metrics_router
from app.api.routes.sessions import router as sessions_router
from app.api.routes.rules import router as rules_router
from app.api.routes.sessions import router as sessions_router
from app.config import settings
from app.database import init_db
from app.security import parse_cors_origins

logger = logging.getLogger("fluxrules.main")

BASE_DIR = Path(__file__).resolve().parent.parent.parent


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage startup and shutdown lifecycle events."""
    # --- Startup ---
    init_db()
    from app.services.audit_scheduler import start_audit_scheduler
    start_audit_scheduler()
    yield
    # --- Shutdown ---
    from app.services.audit_scheduler import stop_audit_scheduler
    stop_audit_scheduler()


app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    lifespan=lifespan,
)

# ---------------------------------------------------------------------------
# CORS — configurable via environment.  Defaults are permissive for local dev
# but can (and should) be locked down via CORS_ALLOWED_ORIGINS in production.
# ---------------------------------------------------------------------------
_cors_origins = parse_cors_origins(settings.CORS_ALLOWED_ORIGINS)
_cors_methods = [m.strip() for m in settings.CORS_ALLOWED_METHODS.split(",") if m.strip()]
_cors_headers = [h.strip() for h in settings.CORS_ALLOWED_HEADERS.split(",") if h.strip()]

if _cors_origins == ["*"] and settings.FLUXRULES_ENV == "production":
    logger.warning(
        "⚠️  CORS_ALLOWED_ORIGINS is set to '*' in production. "
        "This is NOT recommended. Restrict origins via the CORS_ALLOWED_ORIGINS "
        "environment variable."
    )

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=settings.CORS_ALLOW_CREDENTIALS,
    allow_methods=_cors_methods,
    allow_headers=_cors_headers,
)

app.include_router(auth_router, prefix=settings.API_V1_STR)
app.include_router(rules_router, prefix=settings.API_V1_STR)
app.include_router(sessions_router, prefix=settings.API_V1_STR)
app.include_router(events_router, prefix=settings.API_V1_STR)
app.include_router(metrics_router, prefix=settings.API_V1_STR)
app.include_router(dependency_graph_router, prefix=settings.API_V1_STR)
app.include_router(analytics_router, prefix=settings.API_V1_STR)
app.include_router(admin_router, prefix=settings.API_V1_STR)
app.include_router(audit_policy_router, prefix=settings.API_V1_STR)
app.include_router(sessions_router, prefix=settings.API_V1_STR)


@app.get("/health", tags=["API"])
def health() -> dict[str, str]:
    """Return a lightweight health check payload for probes and uptime checks."""
    return {"status": "healthy"}


# Frontend mount is optional so backend/server can run as a standalone SDK-oriented API.
if settings.SERVE_FRONTEND:
    app.mount("/", StaticFiles(directory=BASE_DIR / "frontend", html=True), name="frontend")
