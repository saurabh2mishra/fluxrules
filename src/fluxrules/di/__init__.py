"""Dependency injection factory for FluxRules adapters.

Adapters fall into three groups by their role and failure behavior:

- **Domain-core:** Persistence and Repository adapters.
  Required for the system to function. Fails fast on startup errors.
- **Infrastructure:** Queue and Cache adapters.
  Optional optimizations that default to in-memory. Only the in-memory
  backend is available; any other configured backend raises
  :class:`ConfigurationError` so misconfiguration surfaces at startup.
- **Monitoring:** Observability adapters.
  Optional monitoring. Degrades silently to no-op implementations.

Design:
- Single source of truth for adapter creation
- Swappable implementations via :class:`RuntimeConfig`
- Lazy initialization - adapters created on first access
- Singleton pattern - each adapter created once, reused
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from fluxrules.config import RuntimeConfig
from fluxrules.exceptions import ConfigurationError
from fluxrules.ports.observability import TracerPort
from fluxrules.ports.persistence import RulePersistencePort
from fluxrules.ports.queue import QueuePort
from fluxrules.ports.repository import RulesetRepositoryPort
from fluxrules.ports.rule_cache import RuleCachePort

logger = logging.getLogger(__name__)


class ServiceFactory:
    """Dependency injection factory for all adapters.

    **Domain-core (required)**
        - ``create_persistence_adapter()`` - Rule persistence
        - ``create_repository_adapter()`` - Ruleset repository

        Fails fast on errors. System cannot start without these.

    **Infrastructure (optional)**
        - ``create_queue_adapter()`` - Async task queue
        - ``create_cache_adapter()`` - Rule network cache

        Default to in-memory. An unsupported backend raises
        :class:`ConfigurationError`.

    **Monitoring (optional)**
        - ``create_observability_adapter()`` - Tracing and metrics

        Fails silently, uses no-op implementation if unavailable.

    **Important:** ServiceFactory uses static class methods only.
    Do not instantiate it with ``ServiceFactory()``.

    Usage::

        from fluxrules.di import ServiceFactory

        # Domain-core: Create persistence and repository adapters
        persistence = ServiceFactory.create_persistence_adapter()
        repository = ServiceFactory.create_repository_adapter()

        # Infrastructure: Create queue and cache adapters (optional)
        queue = ServiceFactory.create_queue_adapter()
        cache = ServiceFactory.create_cache_adapter()

        # Monitoring: Create observability adapter (optional)
        observability = ServiceFactory.create_observability_adapter()

        # All adapters are singletons - same instance on subsequent calls
        persistence_again = ServiceFactory.create_persistence_adapter()
        assert persistence is persistence_again

        # Reset all adapters (use in tests or at app shutdown)
        ServiceFactory.reset()

    **FastAPI Integration::

        from fastapi import FastAPI
        from sqlalchemy.orm import sessionmaker

        app = FastAPI()
        SessionLocal = sessionmaker(bind=engine)

        @app.on_event("startup")
        async def startup():
            # Initialize DI with lazy session binding
            ServiceFactory.create_persistence_adapter(
                session_provider=SessionLocal
            )
            ServiceFactory.create_repository_adapter()
            # ... other adapters ...

        @app.on_event("shutdown")
        async def shutdown():
            ServiceFactory.reset()
    """

    _instances: dict[str, Any] = {}

    # ── Lifecycle ────────────────────────────────────────────────────────────

    @classmethod
    def reset(cls) -> None:
        """Reset all adapter instances.

        Calls ``close()`` on any adapter that supports it, then clears
        the registry.  Use in test fixtures to guarantee a clean slate.
        """
        for key, instance in cls._instances.items():
            if hasattr(instance, "close"):
                try:
                    instance.close()
                except Exception:
                    logger.debug("Error closing adapter %s during reset", key)
        cls._instances.clear()

    # ── Domain-Core (Required) ───────────────────────────────────────────────

    @classmethod
    def create_persistence_adapter(
        cls,
        config: RuntimeConfig | None = None,
        *,
        session_provider: Callable | None = None,
    ) -> RulePersistencePort:
        """Create or return the rule persistence adapter.

        This adapter is **required** - the system cannot function without
        rule persistence.  A failure here raises ``RuntimeError`` to
        prevent the application from starting in an inconsistent state.

        Args:
            config: Runtime configuration.  Uses ``RuntimeConfig.default()``
                when *None*.
            session_provider: A callable that returns a SQLAlchemy
                ``Session``.  Required when the backend is ``"postgres"``.
                The adapter calls this each time it needs a session,
                enabling request-scoped or lazy session binding.

        Returns:
            A concrete ``RulePersistencePort`` implementation.

        Raises:
            RuntimeError: If the adapter cannot be created (required
                adapter - fail fast).
        """
        if "persistence" not in cls._instances:
            cfg = config or RuntimeConfig.default()
            try:
                if cfg.persistence.backend == "postgres":
                    from fluxrules.adapters.persistence import (
                        SQLAlchemyPersistenceAdapter,
                    )

                    if session_provider is None:
                        raise ValueError(
                            "PostgreSQL persistence backend requires a 'session_provider' callable"
                        )
                    cls._instances["persistence"] = SQLAlchemyPersistenceAdapter(
                        session_provider=session_provider,
                    )
                    logger.info("Domain-core: created PostgreSQL persistence adapter")
                else:
                    from fluxrules.ports.persistence import InMemoryRulePersistence

                    cls._instances["persistence"] = InMemoryRulePersistence()
                    logger.info("Domain-core: created in-memory persistence adapter")
            except Exception as exc:
                logger.critical("Domain-core FAILED: cannot create persistence adapter: %s", exc)
                raise RuntimeError(f"Cannot start FluxRules without persistence: {exc}") from exc
        return cls._instances["persistence"]

    @classmethod
    def create_repository_adapter(
        cls,
        config: RuntimeConfig | None = None,
        *,
        persistence: RulePersistencePort | None = None,
    ) -> RulesetRepositoryPort:
        """Create or return the ruleset repository adapter.

        This adapter is **required** - rulesets must be queryable for the
        system to function.

        Args:
            config: Runtime configuration.
            persistence: An existing persistence adapter to back a
                database repository.  When *None* and the backend is
                ``"database"``, one is created via
                ``create_persistence_adapter``.

        Returns:
            A concrete ``RulesetRepositoryPort`` implementation.

        Raises:
            RuntimeError: If the adapter cannot be created.
        """
        if "repository" not in cls._instances:
            cfg = config or RuntimeConfig.default()
            try:
                if cfg.repository.backend == "database":
                    from fluxrules.adapters.repository.database import (
                        DatabaseRulesetRepository,
                    )

                    persistence_adapter = persistence or cls.create_persistence_adapter(config)
                    cls._instances["repository"] = DatabaseRulesetRepository(
                        persistence=persistence_adapter,
                    )
                    logger.info("Domain-core: created database-backed repository adapter")
                else:
                    from fluxrules.adapters.repository.in_memory import (
                        InMemoryRulesetRepository,
                    )

                    cls._instances["repository"] = InMemoryRulesetRepository()
                    logger.info("Domain-core: created in-memory repository adapter")
            except Exception as exc:
                logger.critical("Domain-core FAILED: cannot create repository adapter: %s", exc)
                raise RuntimeError(f"Cannot start FluxRules without repository: {exc}") from exc
        return cls._instances["repository"]

    # ── Infrastructure (Optional) ────────────────────────────────────────────

    @classmethod
    def create_queue_adapter(cls, config: RuntimeConfig | None = None) -> QueuePort:
        """Create or return the message queue adapter.

        Optional - the system works without it using local processing.
        Only the ``"memory"`` backend is available; any other configured
        backend raises :class:`ConfigurationError`.
        """
        if "queue" not in cls._instances:
            cfg = config or RuntimeConfig.default()
            if cfg.queue.backend != "memory":
                raise ConfigurationError(
                    f"Queue backend {cfg.queue.backend!r} is not available. "
                    "Supported queue backends: 'memory'."
                )
            from fluxrules.adapters.queues import InMemoryQueueAdapter

            cls._instances["queue"] = InMemoryQueueAdapter()
            logger.info("Infrastructure: created in-memory queue adapter")
        return cls._instances["queue"]

    @classmethod
    def create_cache_adapter(cls, config: RuntimeConfig | None = None) -> RuleCachePort:
        """Create or return the rule cache adapter.

        Optional - the system works without it by recompiling rule
        networks on demand.  Only the ``"memory"`` backend is available;
        any other configured backend raises :class:`ConfigurationError`.
        """
        if "cache" not in cls._instances:
            cfg = config or RuntimeConfig.default()
            if cfg.cache.backend != "memory":
                raise ConfigurationError(
                    f"Cache backend {cfg.cache.backend!r} is not available. "
                    "Supported cache backends: 'memory'."
                )
            from fluxrules.adapters.caches import InMemoryRuleCacheAdapter

            cls._instances["cache"] = InMemoryRuleCacheAdapter(
                max_size=cfg.cache.max_size,
            )
            logger.info("Infrastructure: created in-memory cache adapter")
        return cls._instances["cache"]

    # ── Monitoring (Optional) ────────────────────────────────────────────────

    @classmethod
    def create_observability_adapter(cls, config: RuntimeConfig | None = None) -> TracerPort:
        """Create or return the observability adapter.

        Optional - the system is fully functional without it.  Falls
        back silently to a no-op tracer on failure.
        """
        if "observability" not in cls._instances:
            cfg = config or RuntimeConfig.default()
            try:
                if cfg.observability.backend == "noop":
                    from fluxrules.adapters.observability.noop import NoopTracer

                    cls._instances["observability"] = NoopTracer()
                else:
                    # Future: PrometheusTracer, DatadogTracer
                    from fluxrules.adapters.observability.noop import NoopTracer

                    cls._instances["observability"] = NoopTracer()
                logger.info(
                    "Monitoring: created observability adapter (%s)",
                    cfg.observability.backend,
                )
            except Exception as exc:
                logger.debug("Monitoring: observability adapter failed (%s), using no-op", exc)
                from fluxrules.adapters.observability.noop import NoopTracer

                cls._instances["observability"] = NoopTracer()
        return cls._instances["observability"]

    # ── Accessor helpers ─────────────────────────────────────────────────────

    @classmethod
    def get_persistence(cls) -> RulePersistencePort | None:
        """Get the existing persistence adapter, or *None* if not yet created."""
        return cls._instances.get("persistence")

    @classmethod
    def get_repository(cls) -> RulesetRepositoryPort | None:
        """Get the existing repository adapter, or *None* if not yet created."""
        return cls._instances.get("repository")

    @classmethod
    def get_queue(cls) -> QueuePort | None:
        """Get the existing queue adapter, or *None* if not yet created."""
        return cls._instances.get("queue")

    @classmethod
    def get_cache(cls) -> RuleCachePort | None:
        """Get the existing cache adapter, or *None* if not yet created."""
        return cls._instances.get("cache")

    @classmethod
    def get_observability(cls) -> TracerPort | None:
        """Get the existing observability adapter, or *None* if not yet created."""
        return cls._instances.get("observability")
