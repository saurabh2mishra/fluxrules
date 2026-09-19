"""Health and system status endpoints."""

from fastapi import APIRouter

from fluxrules.services.health import HealthCheckService
from fluxrules.version import __version__

router = APIRouter(tags=["health"])

# Embedded mode: no external queue/cache adapters are attached, so component
# checks report healthy. A deployment that wires real adapters passes them here.
_health_service = HealthCheckService()


@router.get("/health")
def health() -> dict[str, str]:
    """Basic health check."""
    return {"status": "healthy"}


@router.get("/v1/health")
def health_v1() -> dict[str, str]:
    """Health check under the versioned API path."""
    return {"status": "healthy"}


@router.get("/api/v1/system/status")
def system_status() -> dict[str, object]:
    """System status with version info and per-component health."""
    status = _health_service.get_status()
    return {
        "status": "running",
        "version": __version__,
        "engine": "fluxrules",
        "healthy": status["healthy"],
        "components": status["components"],
    }
