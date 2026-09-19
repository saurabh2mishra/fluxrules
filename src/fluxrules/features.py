"""Feature flags for gradual rollout of new capabilities."""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


class FeatureFlags:
    """Feature flag management for FluxRules.

    Enables gradual rollout of new features without code changes.
    Production systems should load flags from config/database.
    """

    _flags: dict[str, bool] = {
        "distributed_evaluation": False,
        "rule_caching": False,
        "queue_enabled": False,
        "circuit_breaker": False,
        "rule_versioning": False,
        "multi_tenancy": False,
        "anomaly_detection": False,
    }

    @classmethod
    def enable(cls, flag: str) -> None:
        """Enable a feature flag."""
        if flag not in cls._flags:
            logger.warning(f"Unknown feature flag: {flag}")
        cls._flags[flag] = True
        logger.info(f"Feature flag enabled: {flag}")

    @classmethod
    def disable(cls, flag: str) -> None:
        """Disable a feature flag."""
        cls._flags[flag] = False
        logger.info(f"Feature flag disabled: {flag}")

    @classmethod
    def is_enabled(cls, flag: str) -> bool:
        """Check if a feature flag is enabled."""
        return cls._flags.get(flag, False)

    @classmethod
    def get_all(cls) -> dict[str, bool]:
        """Return all feature flags and their states."""
        return dict(cls._flags)

    @classmethod
    def reset(cls) -> None:
        """Reset all flags to defaults (for testing)."""
        for key in cls._flags:
            cls._flags[key] = False

    @classmethod
    def load_from_dict(cls, flags: dict[str, bool]) -> None:
        """Load feature flags from a dictionary."""
        for key, value in flags.items():
            cls._flags[key] = value
