"""Behavioral tests for the aggregated health check service."""

from __future__ import annotations

from fluxrules.services.health import HealthCheckService


class _Component:
    def __init__(self, healthy: bool, message: str) -> None:
        self._result = (healthy, message)

    def health_check(self) -> tuple[bool, str]:
        return self._result


def test_embedded_mode_reports_all_components_healthy() -> None:
    status = HealthCheckService().get_status()

    assert status["healthy"] is True
    assert status["status"] == "healthy"
    assert set(status["components"]) == {"queue", "cache", "persistence"}
    assert all(component["healthy"] for component in status["components"].values())


def test_unhealthy_queue_degrades_overall_status() -> None:
    service = HealthCheckService(queue=_Component(False, "queue unreachable"))

    status = service.get_status()

    assert status["healthy"] is False
    assert status["status"] == "degraded"
    assert status["components"]["queue"] == {
        "healthy": False,
        "message": "queue unreachable",
    }
    # An unhealthy queue must not mask a healthy cache/persistence.
    assert status["components"]["cache"]["healthy"] is True
    assert status["components"]["persistence"]["healthy"] is True


def test_configured_cache_health_is_delegated() -> None:
    service = HealthCheckService(cache=_Component(True, "cache ok"))

    assert service.check_cache() == (True, "cache ok")
