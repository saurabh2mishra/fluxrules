"""Port interface for compiled rule network cache."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class RuleCachePort(ABC):
    """Abstract interface for compiled rule network cache.

    Implementations may include Redis, in-memory LRU, or Memcached.
    All implementations must:
    - Handle cache misses gracefully (return None)
    - Support TTL-based expiration
    - Provide invalidation by ruleset
    - Report cache statistics
    """

    @abstractmethod
    def get(self, ruleset_id: int, version: int) -> Any | None:
        """Get compiled rule network from cache.

        Args:
            ruleset_id: The ruleset identifier
            version: The ruleset version

        Returns:
            Compiled network object or None if not cached
        """
        ...

    @abstractmethod
    def set(
        self,
        ruleset_id: int,
        version: int,
        network: Any,
        ttl_seconds: int = 3600,
    ) -> None:
        """Store compiled rule network with TTL.

        Args:
            ruleset_id: The ruleset identifier
            version: The ruleset version
            network: The compiled network object to cache
            ttl_seconds: Time-to-live in seconds (default 1 hour)
        """
        ...

    @abstractmethod
    def invalidate(self, ruleset_id: int) -> None:
        """Invalidate all versions of a ruleset cache."""
        ...

    @abstractmethod
    def get_stats(self) -> dict[str, Any]:
        """Return cache hit/miss rates and memory usage."""
        ...

    @abstractmethod
    def health_check(self) -> tuple[bool, str]:
        """Check cache system health."""
        ...

    @abstractmethod
    def close(self) -> None:
        """Close cache connections."""
        ...
