"""In-memory rule cache adapter for testing and embedded mode."""

from __future__ import annotations

import time
from typing import Any

from fluxrules.ports.rule_cache import RuleCachePort


class InMemoryRuleCacheAdapter(RuleCachePort):
    """In-memory LRU-style cache for compiled rule networks.

    Supports TTL-based expiration. Suitable for testing and single-process mode.
    """

    def __init__(self, max_size: int = 1000) -> None:
        self._cache: dict[str, tuple[Any, float]] = {}  # key -> (value, expire_time)
        self._max_size = max_size
        self._stats = {"hits": 0, "misses": 0}
        self._closed = False

    def _make_key(self, ruleset_id: int, version: int) -> str:
        return f"{ruleset_id}:{version}"

    def get(self, ruleset_id: int, version: int) -> Any | None:
        """Get compiled rule network from cache."""
        if self._closed:
            return None

        key = self._make_key(ruleset_id, version)
        entry = self._cache.get(key)

        if entry is None:
            self._stats["misses"] += 1
            return None

        value, expire_time = entry
        if time.time() > expire_time:
            del self._cache[key]
            self._stats["misses"] += 1
            return None

        self._stats["hits"] += 1
        return value

    def set(
        self,
        ruleset_id: int,
        version: int,
        network: Any,
        ttl_seconds: int = 3600,
    ) -> None:
        """Store compiled rule network with TTL."""
        if self._closed:
            return

        # Evict oldest if at capacity
        if len(self._cache) >= self._max_size:
            oldest_key = next(iter(self._cache))
            del self._cache[oldest_key]

        key = self._make_key(ruleset_id, version)
        self._cache[key] = (network, time.time() + ttl_seconds)

    def invalidate(self, ruleset_id: int) -> None:
        """Invalidate all versions of a ruleset."""
        prefix = f"{ruleset_id}:"
        keys_to_delete = [k for k in self._cache if k.startswith(prefix)]
        for key in keys_to_delete:
            del self._cache[key]

    def get_stats(self) -> dict[str, Any]:
        """Return cache statistics."""
        total = self._stats["hits"] + self._stats["misses"]
        hit_rate = self._stats["hits"] / total if total > 0 else 0.0
        return {
            "hits": self._stats["hits"],
            "misses": self._stats["misses"],
            "hit_rate": hit_rate,
            "size": len(self._cache),
            "max_size": self._max_size,
        }

    def health_check(self) -> tuple[bool, str]:
        """Always healthy for in-memory."""
        if self._closed:
            return False, "Cache adapter is closed"
        return True, "In-memory cache is healthy"

    def close(self) -> None:
        """Mark as closed."""
        self._closed = True
        self._cache.clear()

    def reset(self) -> None:
        """Reset all state (for testing)."""
        self._cache.clear()
        self._stats = {"hits": 0, "misses": 0}
        self._closed = False
