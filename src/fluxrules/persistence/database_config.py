"""Database configuration with environment-aware settings.

Provides environment-specific database configuration for development,
staging, and production environments.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class DatabaseConfig:
    """Database configuration with environment selection.

    Attributes:
        env: Environment mode ("dev", "staging", "prod")
        dev_db_url: Development database URL
        staging_db_url: Staging database URL
        prod_db_url: Production database URL
        pool_size: Minimum connection pool size (default: 10)
        max_overflow: Maximum overflow connections (default: 20)
        pool_recycle: Connection recycle time in seconds (default: 3600)
        echo_sql: Log SQL queries (default: False)
    """

    env: str = "dev"
    dev_db_url: str = "sqlite:///fluxrules_dev.db"
    staging_db_url: str | None = None
    prod_db_url: str | None = None
    pool_size: int = 10
    max_overflow: int = 20
    pool_recycle: int = 3600
    echo_sql: bool = False

    @property
    def db_url(self) -> str:
        """Get database URL for current environment."""
        if self.env == "prod":
            if not self.prod_db_url:
                raise ValueError(
                    "Production database URL not configured. "
                    "Set FLUXRULES_DB_URL environment variable."
                )
            return self.prod_db_url
        elif self.env == "staging":
            if not self.staging_db_url:
                # Fall back to prod URL for staging if not explicitly configured
                if self.prod_db_url:
                    return self.prod_db_url
                raise ValueError(
                    "Staging database URL not configured. "
                    "Set FLUXRULES_STAGING_DB_URL environment variable."
                )
            return self.staging_db_url
        else:  # dev or default
            return self.dev_db_url

    @classmethod
    def from_env(cls) -> DatabaseConfig:
        """Auto-configure from environment variables.

        Environment variables:
            FLUXRULES_ENV: "dev", "staging", or "prod" (default: "dev")
            FLUXRULES_DB_URL: Override any database URL
            FLUXRULES_DEV_DB_URL: Development database URL
            FLUXRULES_STAGING_DB_URL: Staging database URL
            FLUXRULES_PROD_DB_URL: Production database URL
            FLUXRULES_DB_POOL_SIZE: Connection pool size (default: 10)
            FLUXRULES_DB_MAX_OVERFLOW: Max overflow (default: 20)
            FLUXRULES_DB_POOL_RECYCLE: Recycle time in seconds (default: 3600)
            FLUXRULES_DB_ECHO_SQL: Log SQL (default: False)

        Returns:
            Configured DatabaseConfig instance
        """
        env = os.getenv("FLUXRULES_ENV", "dev").lower()

        # Validate environment
        if env not in ("dev", "staging", "prod", "test"):
            logger.warning(
                f"Unknown environment '{env}', defaulting to 'dev'. "
                "Valid values: dev, staging, prod, test"
            )
            env = "dev"

        # Get database URLs with overrides
        dev_db_url = os.getenv("FLUXRULES_DEV_DB_URL", "sqlite:///fluxrules_dev.db")
        staging_db_url = os.getenv("FLUXRULES_STAGING_DB_URL")
        prod_db_url = os.getenv("FLUXRULES_PROD_DB_URL") or os.getenv("FLUXRULES_DB_URL")

        # Handle special test environment
        if env == "test":
            dev_db_url = "sqlite:///:memory:"
            env = "dev"

        # Connection pool settings
        pool_size = int(os.getenv("FLUXRULES_DB_POOL_SIZE", "10"))
        max_overflow = int(os.getenv("FLUXRULES_DB_MAX_OVERFLOW", "20"))
        pool_recycle = int(os.getenv("FLUXRULES_DB_POOL_RECYCLE", "3600"))
        echo_sql = os.getenv("FLUXRULES_DB_ECHO_SQL", "false").lower() == "true"

        config = cls(
            env=env,
            dev_db_url=dev_db_url,
            staging_db_url=staging_db_url,
            prod_db_url=prod_db_url,
            pool_size=pool_size,
            max_overflow=max_overflow,
            pool_recycle=pool_recycle,
            echo_sql=echo_sql,
        )

        logger.info(
            f"DatabaseConfig initialized: env={env}, "
            f"url={config.db_url[:50]}..., "
            f"pool_size={pool_size}, max_overflow={max_overflow}"
        )

        return config

    @classmethod
    def for_testing(cls, in_memory: bool = True) -> DatabaseConfig:
        """Create a test database configuration.

        Args:
            in_memory: If True, use in-memory SQLite. Otherwise, use test.db file.

        Returns:
            Test database configuration
        """
        db_url = "sqlite:///:memory:" if in_memory else "sqlite:///test_fluxrules.db"
        return cls(
            env="dev",
            dev_db_url=db_url,
            echo_sql=False,
        )
