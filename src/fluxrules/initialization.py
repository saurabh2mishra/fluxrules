"""FluxRules application initialization module.

Handles startup configuration including database setup, persistence layer
initialization, and other critical startup tasks.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def initialize_persistence(
    env: str | None = None,
    db_url: str | None = None,
    **kwargs,
) -> None:
    """Initialize the persistence layer for automatic rule storage.

    Should be called once during application startup.

    Args:
        env: Environment mode ("dev", "staging", "prod", "test")
        db_url: Optional override for database URL
        **kwargs: Additional configuration parameters

    Example:
        initialize_persistence(env="prod")

    Note:
        If this is not called explicitly, the persistence manager will
        auto-initialize with default configuration on first use.
    """
    import os

    from fluxrules.persistence import DatabaseConfig, DBConnectionManager

    # Allow override from environment if not provided
    if env is None:
        env = os.getenv("FLUXRULES_ENV", "dev")

    if db_url is None:
        db_url = os.getenv("FLUXRULES_DB_URL")

    try:
        # Create database configuration
        config = DatabaseConfig.from_env()

        # Override with provided values if specified
        if db_url and env == "prod":
            config.prod_db_url = db_url
        elif db_url and env == "staging":
            config.staging_db_url = db_url
        elif db_url:
            config.dev_db_url = db_url

        # Initialize connection manager
        DBConnectionManager.initialize(config)

        # Create all database tables
        manager = DBConnectionManager.get_instance()
        manager.create_all_tables()

        logger.info(
            f"✅ Persistence layer initialized: env={config.env}, db={config.db_url[:50]}..."
        )

    except Exception as e:
        logger.error(f"Failed to initialize persistence layer: {e}", exc_info=True)
        raise


def initialize_fluxrules(
    env: str | None = None,
    db_url: str | None = None,
    enable_persistence: bool = True,
    **kwargs,
) -> None:
    """Complete initialization of FluxRules system.

    Should be called once during application startup.

    Args:
        env: Environment mode ("dev", "staging", "prod", "test")
        db_url: Optional override for database URL
        enable_persistence: Whether to enable automatic persistence (default: True)
        **kwargs: Additional configuration parameters

    Example:
        # During Flask/FastAPI startup
        initialize_fluxrules(env="prod", db_url="postgresql://...")

    Note:
        This is a convenience function that calls all necessary initialization
        functions. For fine-grained control, call individual functions directly.
    """
    logger.info("Initializing FluxRules...")

    if enable_persistence:
        initialize_persistence(env=env, db_url=db_url, **kwargs)
    else:
        logger.info("Persistence layer disabled (in-memory mode)")

    logger.info("✅ FluxRules initialized successfully")


__all__ = [
    "initialize_fluxrules",
    "initialize_persistence",
]
