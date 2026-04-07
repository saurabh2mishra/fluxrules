"""Administrative API routes for platform operations.

These endpoints are restricted to admin users and expose:

* Schema version info and migration history.
* Database health and backend type detection.
* Audit-log integrity verification and retention enforcement.
"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_current_admin
from app.config import settings
from app.database import Base, engine, get_db
from app.models.user import User
from app.schema_manager import get_recorded_version, get_version_history
from app.services.audit_service import AuditService

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/schema")
def schema_info(current_user: User = Depends(get_current_admin)):
    """Return the current and expected schema versions plus migration history."""
    recorded = get_recorded_version(engine)
    return {
        "expected_version": settings.SCHEMA_VERSION,
        "recorded_version": recorded,
        "match": recorded == settings.SCHEMA_VERSION,
        "history": get_version_history(engine),
    }


@router.get("/db/health")
def db_health(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin),
):
    """Return database connectivity and backend type diagnostics."""
    url = str(engine.url)
    backend = "sqlite" if "sqlite" in url else "postgresql" if "postgres" in url else "other"
    is_fallback = backend == "sqlite" and "sqlite" not in settings.DATABASE_URL

    return {
        "backend": backend,
        "url_masked": url.split("@")[-1] if "@" in url else url,
        "is_fallback": is_fallback,
        "fallback_enabled": settings.DB_FALLBACK_ENABLED,
        "environment": settings.FLUXRULES_ENV,
    }


@router.get("/audit/integrity")
def audit_integrity(
    limit: int = 100,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin),
):
    """Spot-check integrity hashes of recent audit log entries."""
    svc = AuditService(db)
    return svc.verify_recent(limit=limit)


@router.post("/audit/retention")
def audit_retention(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin),
):
    """Apply the configured audit retention policy and return purge count."""
    svc = AuditService(db)
    purged = svc.apply_retention_policy()
    return {
        "retention_days": settings.AUDIT_RETENTION_DAYS,
        "rows_purged": purged,
    }
