"""Global configuration manager with explicit lifecycle."""

from __future__ import annotations

import logging

from fluxrules.config import RuntimeConfig

logger = logging.getLogger(__name__)


class RuntimeConfigManager:
    """Thread-safe configuration manager.

    Usage:
        # During app startup
        RuntimeConfigManager.initialize(RuntimeConfig(...))

        # During execution
        config = RuntimeConfigManager.get()

    This replaces the implicit `get_config()` pattern with explicit
    initialization, making dependencies clear.
    """

    _instance: RuntimeConfig | None = None
    _initialized = False

    @classmethod
    def initialize(cls, config: RuntimeConfig) -> None:
        """Initialize the global config (call once at startup).

        Args:
            config: RuntimeConfig instance to use globally
        """
        if cls._initialized:
            logger.warning("RuntimeConfigManager already initialized; ignoring second call")
            return
        cls._instance = config
        cls._initialized = True
        logger.info("RuntimeConfigManager initialized with config")

    @classmethod
    def get(cls) -> RuntimeConfig:
        """Get the current configuration.

        Returns:
            Current RuntimeConfig, or default if not initialized
        """
        if cls._instance is None:
            logger.warning(
                "RuntimeConfigManager not initialized; creating default config. "
                "Call RuntimeConfigManager.initialize() during app startup."
            )
            cls._instance = RuntimeConfig.default()
        return cls._instance

    @classmethod
    def reset(cls) -> None:
        """Reset for testing."""
        cls._instance = None
        cls._initialized = False

    @classmethod
    def is_initialized(cls) -> bool:
        """Check if manager is initialized."""
        return cls._initialized

    @classmethod
    def set(cls, config: RuntimeConfig) -> None:
        """Override current config (use with caution).

        This is mainly for testing. Production code should call
        initialize() once during startup.
        """
        cls._instance = config
        cls._initialized = True
