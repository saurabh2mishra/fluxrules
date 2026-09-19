"""Unified application configuration (12-factor compliant)."""

from __future__ import annotations

import os
from dataclasses import dataclass, field

# Domain-Core Configuration


@dataclass
class PersistenceConfig:
    """Configuration for rule persistence adapter (domain-core).

    Controls how rules are stored and retrieved. This is a required
    adapter - the system cannot function without persistence.
    """

    backend: str = "memory"  # "memory" or "postgres"
    database_url: str | None = None

    @classmethod
    def from_env(cls) -> PersistenceConfig:
        return cls(
            backend=os.getenv("PERSISTENCE_BACKEND", "memory"),
            database_url=os.getenv("DATABASE_URL"),
        )


@dataclass
class RepositoryConfig:
    """Configuration for repository adapter (domain-core).

    Controls how rulesets are queried and listed. This is a required
    adapter - the system cannot function without a repository.
    """

    backend: str = "memory"  # "memory" or "database"

    @classmethod
    def from_env(cls) -> RepositoryConfig:
        return cls(
            backend=os.getenv("REPOSITORY_BACKEND", "memory"),
        )


# Infrastructure Configuration


@dataclass
class QueueConfig:
    """Configuration for queue adapter (infrastructure).

    Controls fact distribution across systems. Optional - the system
    works without it using local in-memory processing.
    """

    backend: str = "memory"  # only "memory" is supported
    bootstrap_servers: list[str] = field(default_factory=lambda: ["localhost:9092"])
    facts_topic: str = "facts"
    commands_topic: str = "commands"
    metrics_topic: str = "metrics"
    consumer_group: str = "fluxrules-workers"

    @classmethod
    def from_env(cls) -> QueueConfig:
        return cls(
            backend=os.getenv("QUEUE_BACKEND", "memory"),
            bootstrap_servers=os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092").split(","),
            consumer_group=os.getenv("KAFKA_CONSUMER_GROUP", "fluxrules-workers"),
        )


@dataclass
class CacheConfig:
    """Configuration for cache adapter (infrastructure).

    Controls compiled rule network caching. Optional - the system
    works without it by recompiling rule networks on demand.
    """

    backend: str = "memory"  # only "memory" is supported
    host: str = "localhost"
    port: int = 6379
    password: str | None = None
    max_size: int = 1000
    ttl_seconds: int = 3600

    @classmethod
    def from_env(cls) -> CacheConfig:
        return cls(
            backend=os.getenv("CACHE_BACKEND", "memory"),
            host=os.getenv("REDIS_HOST", "localhost"),
            port=int(os.getenv("REDIS_PORT", "6379")),
            password=os.getenv("REDIS_PASSWORD"),
            max_size=int(os.getenv("CACHE_MAX_SIZE", "1000")),
            ttl_seconds=int(os.getenv("CACHE_TTL_SECONDS", "3600")),
        )


# Observability Configuration


@dataclass
class ObservabilityConfig:
    """Configuration for observability adapter (monitoring).

    Controls tracing and metrics collection. Optional - the system
    works without it; monitoring is informational only.
    """

    backend: str = "noop"  # "noop" or "prometheus" (future)

    @classmethod
    def from_env(cls) -> ObservabilityConfig:
        return cls(
            backend=os.getenv("OBSERVABILITY_BACKEND", "noop"),
        )


# Unified Runtime Configuration


@dataclass
class RuntimeConfig:
    """Unified runtime configuration.

    Adapters are organized into three groups by role and failure behavior:

    - **Domain-core:** Required. System fails fast on startup
      if these cannot be created.
    - **Infrastructure:** Optional. System degrades gracefully
      to in-memory fallbacks if these fail.
    - **Monitoring:** Optional. System continues silently
      with no-op implementations if these fail.

    Priority order for values:
    1. Environment variables
    2. Defaults
    """

    deployment_mode: str = "single-process"  # or "distributed"

    # Domain-core (required)
    persistence: PersistenceConfig = field(
        default_factory=PersistenceConfig.from_env,
    )
    repository: RepositoryConfig = field(
        default_factory=RepositoryConfig.from_env,
    )

    # Infrastructure (optional)
    queue: QueueConfig = field(default_factory=QueueConfig.from_env)
    cache: CacheConfig = field(default_factory=CacheConfig.from_env)

    # Monitoring (optional)
    observability: ObservabilityConfig = field(
        default_factory=ObservabilityConfig.from_env,
    )

    log_level: str = "INFO"
    metrics_enabled: bool = True
    health_check_interval_seconds: int = 30

    @classmethod
    def from_env(cls) -> RuntimeConfig:
        """Load configuration from environment variables."""
        return cls(
            deployment_mode=os.getenv("DEPLOYMENT_MODE", "single-process"),
            log_level=os.getenv("LOG_LEVEL", "INFO"),
            metrics_enabled=os.getenv("METRICS_ENABLED", "true").lower() == "true",
            health_check_interval_seconds=int(os.getenv("HEALTH_CHECK_INTERVAL", "30")),
        )

    @classmethod
    def default(cls) -> RuntimeConfig:
        """Create default in-memory configuration (no external dependencies)."""
        return cls(
            deployment_mode="single-process",
            persistence=PersistenceConfig(backend="memory"),
            repository=RepositoryConfig(backend="memory"),
            queue=QueueConfig(backend="memory"),
            cache=CacheConfig(backend="memory"),
            observability=ObservabilityConfig(backend="noop"),
        )


from fluxrules.config.deployment import (  # noqa: E402  (deferred: avoids circular import)
    ConfigValidationError,
    DeploymentConfig,
    DeploymentType,
)
from fluxrules.config.manager import (  # noqa: E402  (deferred: avoids circular import)
    RuntimeConfigManager,
)

__all__ = [
    "CacheConfig",
    "ConfigValidationError",
    "DeploymentConfig",
    "DeploymentType",
    "ObservabilityConfig",
    "PersistenceConfig",
    "QueueConfig",
    "RepositoryConfig",
    "RuntimeConfig",
    "RuntimeConfigManager",
]
