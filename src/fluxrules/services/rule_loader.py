"""Intelligent rule loading with fallback chain."""

from __future__ import annotations

import logging
from typing import Any

from fluxrules.ports.rule_cache import RuleCachePort

logger = logging.getLogger(__name__)


class RuleLoader:
    """Intelligent rule loading with fallback chain.

    Chain:
    1. Cache (fastest, may miss)
    2. Repository (authoritative, slower)
    3. Local in-memory cache (degraded mode, last resort)

    This ensures high availability even if cache or repository fails.
    """

    def __init__(
        self,
        cache: RuleCachePort,
        repository: Any,
        local_cache: dict[str, Any] | None = None,
    ) -> None:
        self.cache = cache
        self.repository = repository
        self.local_cache: dict[str, Any] = local_cache if local_cache is not None else {}

    def load_rules(self, ruleset_id: int, version: int = 1) -> Any | None:
        """Load rules with fallback chain.

        Returns:
            Compiled rule network or None if all sources fail.
        """
        # Try 1: Cache (O(1), may fail)
        try:
            network = self.cache.get(ruleset_id, version)
            if network is not None:
                logger.debug(f"Loaded from cache: ruleset {ruleset_id} v{version}")
                return network
        except Exception as e:
            logger.warning(f"Cache failed for ruleset {ruleset_id}: {e}")

        # Try 2: Repository (authoritative)
        try:
            ruleset = self.repository.get(ruleset_id)
            if ruleset is not None:
                # Populate cache for future requests
                try:
                    self.cache.set(ruleset_id, version, ruleset)
                except Exception as e:
                    logger.warning(f"Failed to cache ruleset {ruleset_id}: {e}")
                # Store in local cache
                self.local_cache[f"{ruleset_id}:{version}"] = ruleset
                logger.debug(f"Loaded from repository: ruleset {ruleset_id}")
                return ruleset
        except Exception as e:
            logger.warning(f"Repository failed for ruleset {ruleset_id}: {e}")

        # Try 3: Local in-memory fallback
        key = f"{ruleset_id}:{version}"
        if key in self.local_cache:
            logger.warning(f"Using local cache (degraded mode): ruleset {ruleset_id}")
            return self.local_cache[key]

        # All sources failed
        logger.error(f"Failed to load rules from all sources: ruleset {ruleset_id}")
        return None
