"""Health check service implementation."""

from __future__ import annotations

import logging
from typing import Any

from fluxrules.ports.health import HealthCheckPort
from fluxrules.ports.queue import QueuePort
from fluxrules.ports.rule_cache import RuleCachePort

logger = logging.getLogger(__name__)


class HealthCheckService(HealthCheckPort):
    """Aggregated health check across all system components."""

    def __init__(
        self,
        queue: QueuePort | None = None,
        cache: RuleCachePort | None = None,
    ) -> None:
        self._queue = queue
        self._cache = cache

    def check_queue(self) -> tuple[bool, str]:
        """Check queue health."""
        if self._queue is None:
            return True, "Queue not configured (embedded mode)"
        return self._queue.health_check()

    def check_cache(self) -> tuple[bool, str]:
        """Check cache health."""
        if self._cache is None:
            return True, "Cache not configured (embedded mode)"
        return self._cache.health_check()

    def check_persistence(self) -> tuple[bool, str]:
        """Check persistence layer health."""
        # In embedded mode, persistence is always healthy
        return True, "Persistence is healthy"

    def get_status(self) -> dict[str, Any]:
        """Return overall system health status."""
        queue_ok, queue_msg = self.check_queue()
        cache_ok, cache_msg = self.check_cache()
        persist_ok, persist_msg = self.check_persistence()

        all_healthy = queue_ok and cache_ok and persist_ok

        return {
            "healthy": all_healthy,
            "status": "healthy" if all_healthy else "degraded",
            "components": {
                "queue": {"healthy": queue_ok, "message": queue_msg},
                "cache": {"healthy": cache_ok, "message": cache_msg},
                "persistence": {"healthy": persist_ok, "message": persist_msg},
            },
        }
