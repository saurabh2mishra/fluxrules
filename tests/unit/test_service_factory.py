"""Tests for the ServiceFactory.

Covers:
- Domain-core: persistence and repository adapters
- Infrastructure: queue and cache adapters
- Monitoring: observability adapter
- Lifecycle: reset, singleton, lazy init
- Session provider: lazy session binding for SQLAlchemy
"""

from __future__ import annotations

import pytest

from fluxrules.config import (
    CacheConfig,
    ObservabilityConfig,
    PersistenceConfig,
    QueueConfig,
    RepositoryConfig,
    RuntimeConfig,
)
from fluxrules.di import ServiceFactory
from fluxrules.exceptions import ConfigurationError
from fluxrules.ports.observability import TracerPort
from fluxrules.ports.persistence import InMemoryRulePersistence, RulePersistencePort
from fluxrules.ports.queue import QueuePort
from fluxrules.ports.repository import RulesetRepositoryPort
from fluxrules.ports.rule_cache import RuleCachePort


@pytest.fixture(autouse=True)
def _reset_di():
    """Reset the ServiceFactory between every test."""
    yield
    ServiceFactory.reset()


def _memory_config() -> RuntimeConfig:
    """Return an all-in-memory runtime configuration."""
    return RuntimeConfig.default()


# Persistence


class TestPersistenceAdapter:
    """Domain-core: create_persistence_adapter."""

    def test_creates_in_memory_adapter(self):
        adapter = ServiceFactory.create_persistence_adapter(config=_memory_config())
        assert isinstance(adapter, RulePersistencePort)
        assert isinstance(adapter, InMemoryRulePersistence)

    def test_singleton_returns_same_instance(self):
        first = ServiceFactory.create_persistence_adapter(config=_memory_config())
        second = ServiceFactory.create_persistence_adapter(config=_memory_config())
        assert first is second

    def test_get_persistence_before_create_returns_none(self):
        assert ServiceFactory.get_persistence() is None

    def test_get_persistence_after_create(self):
        adapter = ServiceFactory.create_persistence_adapter(config=_memory_config())
        assert ServiceFactory.get_persistence() is adapter

    def test_postgres_without_session_provider_raises(self):
        cfg = RuntimeConfig(
            persistence=PersistenceConfig(backend="postgres"),
            repository=RepositoryConfig(backend="memory"),
            queue=QueueConfig(backend="memory"),
            cache=CacheConfig(backend="memory"),
            observability=ObservabilityConfig(backend="noop"),
        )
        with pytest.raises(RuntimeError, match="Cannot start FluxRules"):
            ServiceFactory.create_persistence_adapter(config=cfg)

    def test_postgres_with_session_provider(self):
        """Verify the adapter is created when a session_provider is given.

        We use a dummy provider here; actual DB integration is tested
        separately.
        """
        from unittest.mock import MagicMock

        mock_session = MagicMock()
        cfg = RuntimeConfig(
            persistence=PersistenceConfig(backend="postgres"),
            repository=RepositoryConfig(backend="memory"),
            queue=QueueConfig(backend="memory"),
            cache=CacheConfig(backend="memory"),
            observability=ObservabilityConfig(backend="noop"),
        )
        adapter = ServiceFactory.create_persistence_adapter(
            config=cfg, session_provider=lambda: mock_session
        )
        assert isinstance(adapter, RulePersistencePort)

    def test_unknown_backend_falls_back_to_memory(self):
        cfg = RuntimeConfig(
            persistence=PersistenceConfig(backend="unknown_db"),
            repository=RepositoryConfig(backend="memory"),
            queue=QueueConfig(backend="memory"),
            cache=CacheConfig(backend="memory"),
            observability=ObservabilityConfig(backend="noop"),
        )
        adapter = ServiceFactory.create_persistence_adapter(config=cfg)
        assert isinstance(adapter, InMemoryRulePersistence)


# Repository


class TestRepositoryAdapter:
    """Domain-core: create_repository_adapter."""

    def test_creates_in_memory_repository(self):
        adapter = ServiceFactory.create_repository_adapter(config=_memory_config())
        assert isinstance(adapter, RulesetRepositoryPort)

    def test_singleton_returns_same_instance(self):
        first = ServiceFactory.create_repository_adapter(config=_memory_config())
        second = ServiceFactory.create_repository_adapter(config=_memory_config())
        assert first is second

    def test_get_repository_before_create_returns_none(self):
        assert ServiceFactory.get_repository() is None

    def test_get_repository_after_create(self):
        adapter = ServiceFactory.create_repository_adapter(config=_memory_config())
        assert ServiceFactory.get_repository() is adapter

    def test_database_backend_creates_database_repository(self):
        from fluxrules.adapters.repository.database import DatabaseRulesetRepository

        cfg = RuntimeConfig(
            persistence=PersistenceConfig(backend="memory"),
            repository=RepositoryConfig(backend="database"),
            queue=QueueConfig(backend="memory"),
            cache=CacheConfig(backend="memory"),
            observability=ObservabilityConfig(backend="noop"),
        )
        adapter = ServiceFactory.create_repository_adapter(config=cfg)
        assert isinstance(adapter, DatabaseRulesetRepository)

    def test_database_backend_uses_injected_persistence(self):
        from fluxrules.adapters.repository.database import DatabaseRulesetRepository

        persistence = InMemoryRulePersistence()
        cfg = RuntimeConfig(
            persistence=PersistenceConfig(backend="memory"),
            repository=RepositoryConfig(backend="database"),
            queue=QueueConfig(backend="memory"),
            cache=CacheConfig(backend="memory"),
            observability=ObservabilityConfig(backend="noop"),
        )
        adapter = ServiceFactory.create_repository_adapter(config=cfg, persistence=persistence)
        assert isinstance(adapter, DatabaseRulesetRepository)


# Queue


class TestQueueAdapter:
    """Infrastructure: create_queue_adapter."""

    def test_creates_queue_adapter(self):
        adapter = ServiceFactory.create_queue_adapter(config=_memory_config())
        assert isinstance(adapter, QueuePort)

    def test_singleton(self):
        first = ServiceFactory.create_queue_adapter(config=_memory_config())
        second = ServiceFactory.create_queue_adapter(config=_memory_config())
        assert first is second

    def test_get_queue(self):
        assert ServiceFactory.get_queue() is None
        adapter = ServiceFactory.create_queue_adapter(config=_memory_config())
        assert ServiceFactory.get_queue() is adapter

    def test_unsupported_backend_raises(self):
        cfg = RuntimeConfig(queue=QueueConfig(backend="kafka"))
        with pytest.raises(ConfigurationError, match="Queue backend 'kafka'"):
            ServiceFactory.create_queue_adapter(config=cfg)
        assert ServiceFactory.get_queue() is None


# Cache


class TestCacheAdapter:
    """Infrastructure: create_cache_adapter."""

    def test_creates_cache_adapter(self):
        adapter = ServiceFactory.create_cache_adapter(config=_memory_config())
        assert isinstance(adapter, RuleCachePort)

    def test_singleton(self):
        first = ServiceFactory.create_cache_adapter(config=_memory_config())
        second = ServiceFactory.create_cache_adapter(config=_memory_config())
        assert first is second

    def test_get_cache(self):
        assert ServiceFactory.get_cache() is None
        adapter = ServiceFactory.create_cache_adapter(config=_memory_config())
        assert ServiceFactory.get_cache() is adapter

    def test_unsupported_backend_raises(self):
        cfg = RuntimeConfig(cache=CacheConfig(backend="redis"))
        with pytest.raises(ConfigurationError, match="Cache backend 'redis'"):
            ServiceFactory.create_cache_adapter(config=cfg)
        assert ServiceFactory.get_cache() is None


# Observability


class TestObservabilityAdapter:
    """Monitoring: create_observability_adapter."""

    def test_creates_noop_tracer(self):
        adapter = ServiceFactory.create_observability_adapter(config=_memory_config())
        assert isinstance(adapter, TracerPort)

    def test_singleton(self):
        first = ServiceFactory.create_observability_adapter(config=_memory_config())
        second = ServiceFactory.create_observability_adapter(config=_memory_config())
        assert first is second

    def test_get_observability(self):
        assert ServiceFactory.get_observability() is None
        adapter = ServiceFactory.create_observability_adapter(config=_memory_config())
        assert ServiceFactory.get_observability() is adapter


# Lifecycle


class TestLifecycle:
    """ServiceFactory lifecycle and reset."""

    def test_reset_clears_all_instances(self):
        cfg = _memory_config()
        ServiceFactory.create_persistence_adapter(config=cfg)
        ServiceFactory.create_repository_adapter(config=cfg)
        ServiceFactory.create_queue_adapter(config=cfg)
        ServiceFactory.create_cache_adapter(config=cfg)
        ServiceFactory.create_observability_adapter(config=cfg)

        ServiceFactory.reset()

        assert ServiceFactory.get_persistence() is None
        assert ServiceFactory.get_repository() is None
        assert ServiceFactory.get_queue() is None
        assert ServiceFactory.get_cache() is None
        assert ServiceFactory.get_observability() is None

    def test_reset_calls_close_on_adapters(self):
        from unittest.mock import MagicMock

        # Inject a mock adapter with close()
        mock = MagicMock()
        ServiceFactory._instances["persistence"] = mock

        ServiceFactory.reset()
        mock.close.assert_called_once()

    def test_new_adapter_created_after_reset(self):
        first = ServiceFactory.create_persistence_adapter(config=_memory_config())
        ServiceFactory.reset()
        second = ServiceFactory.create_persistence_adapter(config=_memory_config())
        assert first is not second


# DatabaseRulesetRepository


class TestDatabaseRulesetRepository:
    """Integration test for DatabaseRulesetRepository backed by InMemoryRulePersistence."""

    def test_save_and_get_ruleset(self):
        from fluxrules.adapters.repository.database import DatabaseRulesetRepository
        from fluxrules.domain.models import EngineRule, RuleCondition, Ruleset

        persistence = InMemoryRulePersistence()
        repo = DatabaseRulesetRepository(persistence=persistence)

        rule = EngineRule(
            id=1,
            name="r1",
            conditions=(RuleCondition(fact="x", operator="==", value=1),),
            actions=("a1",),
            group="grp",
        )
        ruleset = Ruleset(group="grp", rules=(rule,))
        repo.save(ruleset)

        loaded = repo.get("grp")
        assert loaded is not None
        assert len(loaded.rules) == 1

    def test_get_nonexistent_returns_none(self):
        from fluxrules.adapters.repository.database import DatabaseRulesetRepository

        persistence = InMemoryRulePersistence()
        repo = DatabaseRulesetRepository(persistence=persistence)
        assert repo.get("nope") is None

    def test_list_all(self):
        from fluxrules.adapters.repository.database import DatabaseRulesetRepository
        from fluxrules.domain.models import EngineRule, RuleCondition, Ruleset

        persistence = InMemoryRulePersistence()
        repo = DatabaseRulesetRepository(persistence=persistence)

        rule = EngineRule(
            id=1,
            name="r1",
            conditions=(RuleCondition(fact="x", operator="==", value=1),),
            actions=("a1",),
            group="grp",
        )
        ruleset = Ruleset(group="grp", rules=(rule,))
        repo.save(ruleset)

        result = repo.list_all()
        assert len(result) >= 1

    def test_delete(self):
        from fluxrules.adapters.repository.database import DatabaseRulesetRepository
        from fluxrules.domain.models import EngineRule, RuleCondition, Ruleset

        persistence = InMemoryRulePersistence()
        repo = DatabaseRulesetRepository(persistence=persistence)

        rule = EngineRule(
            id=1,
            name="r1",
            conditions=(RuleCondition(fact="x", operator="==", value=1),),
            actions=("a1",),
            group="del_grp",
        )
        ruleset = Ruleset(group="del_grp", rules=(rule,))
        repo.save(ruleset)

        assert repo.delete("del_grp") is True
        assert repo.get("del_grp") is None

    def test_delete_nonexistent_returns_false(self):
        from fluxrules.adapters.repository.database import DatabaseRulesetRepository

        persistence = InMemoryRulePersistence()
        repo = DatabaseRulesetRepository(persistence=persistence)
        assert repo.delete("nope") is False


# PersistenceService.create_default


class TestPersistenceServiceDefault:
    """PersistenceService.create_default() uses DI correctly."""

    def test_create_default_returns_service(self):
        from fluxrules.services.persistence_service import PersistenceService

        service = PersistenceService.create_default()
        assert isinstance(service, PersistenceService)

    def test_create_default_save_and_load(self):
        from fluxrules.domain.models import EngineRule, RuleCondition
        from fluxrules.services.persistence_service import PersistenceService

        service = PersistenceService.create_default()
        rule = EngineRule(
            id=1,
            name="svc_test",
            conditions=(RuleCondition(fact="x", operator="==", value=1),),
            actions=("a1",),
        )
        rule_id = service.save_rule(rule)
        loaded = service.load_rule(rule_id)
        assert loaded is not None
        assert loaded.name == "svc_test"


# SQLAlchemy Lazy Session Binding


class TestLazySessionBinding:
    """SQLAlchemyPersistenceAdapter session_provider pattern."""

    def test_raises_without_db_or_provider(self):
        from fluxrules.adapters.persistence.sqlalchemy_adapter import (
            SQLAlchemyPersistenceAdapter,
        )

        with pytest.raises(ValueError, match="requires either"):
            SQLAlchemyPersistenceAdapter()

    def test_session_provider_called_on_db_access(self):
        from unittest.mock import MagicMock

        from fluxrules.adapters.persistence.sqlalchemy_adapter import (
            SQLAlchemyPersistenceAdapter,
        )

        mock_session = MagicMock()
        provider = MagicMock(return_value=mock_session)

        adapter = SQLAlchemyPersistenceAdapter(session_provider=provider)

        # Accessing .db should call the provider
        session = adapter.db
        provider.assert_called_once()
        assert session is mock_session

    def test_direct_db_mode_still_works(self):
        from unittest.mock import MagicMock

        from fluxrules.adapters.persistence.sqlalchemy_adapter import (
            SQLAlchemyPersistenceAdapter,
        )

        mock_session = MagicMock()
        adapter = SQLAlchemyPersistenceAdapter(db=mock_session)
        assert adapter.db is mock_session
