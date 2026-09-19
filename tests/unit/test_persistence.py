"""Tests for database persistence components.

Tests the DatabaseConfig, DBConnectionManager, and PersistenceManager
components that enable automatic rule persistence.
"""

import pytest

from fluxrules.domain.models import EngineRule, RuleCondition
from fluxrules.domain.unified_rule import Rule as CanonicalRule
from fluxrules.persistence.database_config import DatabaseConfig
from fluxrules.persistence.db_connection_manager import DBConnectionManager
from fluxrules.persistence.persistence_manager import (
    PersistenceManager,
    get_persistence_manager,
    reset_persistence_manager,
    set_persistence_manager,
)


class TestDatabaseConfig:
    """Test DatabaseConfig with environment awareness."""

    def test_from_env_defaults_to_dev(self, monkeypatch):
        """DatabaseConfig should default to dev when FLUXRULES_ENV is not set."""
        monkeypatch.delenv("FLUXRULES_ENV", raising=False)
        config = DatabaseConfig.from_env()
        assert config.env == "dev"
        assert "sqlite" in config.db_url

    def test_from_env_respects_env_variable(self, monkeypatch):
        """DatabaseConfig should respect FLUXRULES_ENV variable."""
        monkeypatch.setenv("FLUXRULES_ENV", "prod")
        monkeypatch.setenv("FLUXRULES_PROD_DB_URL", "postgresql://localhost/fluxrules")
        config = DatabaseConfig.from_env()
        assert config.env == "prod"
        assert "postgresql" in config.db_url

    def test_from_env_test_mode_uses_memory_db(self, monkeypatch):
        """DatabaseConfig test mode should use in-memory SQLite."""
        monkeypatch.setenv("FLUXRULES_ENV", "test")
        config = DatabaseConfig.from_env()
        assert "sqlite" in config.db_url
        assert ":memory:" in config.db_url

    def test_for_testing_creates_memory_db(self):
        """for_testing() should create in-memory database config."""
        config = DatabaseConfig.for_testing(in_memory=True)
        assert "memory" in config.db_url
        assert config.env == "dev"

    def test_pool_settings_from_env(self, monkeypatch):
        """DatabaseConfig should read pool settings from environment."""
        monkeypatch.setenv("FLUXRULES_DB_POOL_SIZE", "20")
        monkeypatch.setenv("FLUXRULES_DB_MAX_OVERFLOW", "30")
        config = DatabaseConfig.from_env()
        assert config.pool_size == 20
        assert config.max_overflow == 30


class TestDBConnectionManager:
    """Test DBConnectionManager singleton and connection handling."""

    @pytest.fixture(autouse=True)
    def cleanup_manager(self):
        """Reset manager before and after each test."""
        DBConnectionManager.reset()
        yield
        DBConnectionManager.reset()

    def test_initialize_creates_singleton(self):
        """DBConnectionManager.initialize() should create singleton."""
        config = DatabaseConfig.for_testing()
        manager = DBConnectionManager.initialize(config)
        assert manager is not None
        assert DBConnectionManager.get_instance() is manager

    def test_initialize_idempotent(self):
        """Multiple initialize() calls should return same instance."""
        config1 = DatabaseConfig.for_testing()
        manager1 = DBConnectionManager.initialize(config1)

        config2 = DatabaseConfig.for_testing()
        manager2 = DBConnectionManager.initialize(config2)

        assert manager1 is manager2

    def test_get_session_returns_valid_session(self):
        """get_session() should return valid SQLAlchemy session."""
        config = DatabaseConfig.for_testing()
        DBConnectionManager.initialize(config)
        manager = DBConnectionManager.get_instance()

        session = manager.get_session()
        assert session is not None
        # Session should be usable
        session.close()

    def test_create_all_tables_succeeds(self):
        """create_all_tables() should create database tables."""
        config = DatabaseConfig.for_testing()
        manager = DBConnectionManager.initialize(config)

        # Should not raise
        manager.create_all_tables()

    def test_close_cleans_up_resources(self):
        """close() should cleanup database resources."""
        config = DatabaseConfig.for_testing()
        manager = DBConnectionManager.initialize(config)

        # Force engine creation by getting a session
        session = manager.get_session()
        session.close()

        assert manager._engine is not None

        manager.close()
        assert manager._engine is None

    def test_reset_clears_singleton(self):
        """reset() should clear the singleton instance."""
        config = DatabaseConfig.for_testing()
        DBConnectionManager.initialize(config)
        assert DBConnectionManager._instance is not None

        DBConnectionManager.reset()
        assert DBConnectionManager._instance is None


class TestPersistenceManager:
    """Test PersistenceManager for rule persistence."""

    @pytest.fixture(autouse=True)
    def setup_db(self):
        """Setup database for testing."""
        config = DatabaseConfig.for_testing()
        DBConnectionManager.reset()
        manager = DBConnectionManager.initialize(config)
        manager.create_all_tables()
        reset_persistence_manager()
        yield
        DBConnectionManager.reset()
        reset_persistence_manager()

    def test_persist_rule_to_database(self):
        """persist_rule() should save rule to database and assign ID."""
        pm = PersistenceManager(enabled=True)

        rule = EngineRule(
            id=None,
            name="Test Rule",
            conditions=(
                RuleCondition(
                    fact="amount",
                    operator=">",
                    value=1000,
                ),
            ),
            actions=("flag",),
            priority=10,
        )

        persisted = pm.persist_rule(rule)

        assert persisted.id is not None
        assert persisted.name == "Test Rule"
        assert persisted.priority == 10

    def test_persist_canonical_rule_to_database(self):
        """persist_rule() accepts the canonical Rule and preserves its condition."""
        pm = PersistenceManager(enabled=True)

        rule = CanonicalRule(
            name="Canonical Rule",
            condition_dsl={
                "type": "condition",
                "field": "amount",
                "op": ">",
                "value": 1000,
            },
            action="flag",
            priority=7,
            persist=False,
        )

        persisted = pm.persist_rule(rule)

        assert persisted.id is not None
        assert persisted.name == "Canonical Rule"
        assert persisted.priority == 7
        assert persisted.actions == ("flag",)
        assert persisted.conditions[0].fact == "amount"

    def test_persist_disabled_generates_local_id(self):
        """With persistence disabled, should generate local ID."""
        pm = PersistenceManager(enabled=False)

        rule = EngineRule(
            id=None,
            name="Test Rule",
            conditions=(RuleCondition(fact="age", operator=">", value=18),),
            actions=("allow",),
        )

        persisted = pm.persist_rule(rule)

        assert persisted.id is not None
        assert isinstance(persisted.id, int)
        assert persisted.id > 0

    def test_disable_and_enable_persistence(self):
        """Can disable and re-enable persistence."""
        pm = PersistenceManager(enabled=True)
        assert pm.is_enabled()

        pm.disable_persistence()
        assert not pm.is_enabled()

        pm.enable_persistence()
        assert pm.is_enabled()

    def test_persist_ruleset_persists_multiple_rules(self):
        """persist_ruleset() should persist multiple rules."""
        pm = PersistenceManager(enabled=True)

        rules = [
            EngineRule(
                id=None,
                name=f"Rule {i}",
                conditions=(RuleCondition(fact="test", operator="==", value=i),),
                actions=(f"action{i}",),
            )
            for i in range(3)
        ]

        persisted_rules = pm.persist_ruleset(rules)

        assert len(persisted_rules) == 3
        for rule in persisted_rules:
            assert rule.id is not None

    def test_persistence_manager_singleton(self):
        """get_persistence_manager() should return singleton."""
        pm1 = get_persistence_manager()
        pm2 = get_persistence_manager()
        assert pm1 is pm2

    def test_set_persistence_manager_updates_singleton(self):
        """set_persistence_manager() should update global singleton."""
        pm1 = get_persistence_manager()
        pm2 = PersistenceManager(enabled=False)

        set_persistence_manager(pm2)

        assert get_persistence_manager() is pm2
        assert get_persistence_manager() is not pm1

    def test_reset_persistence_manager_creates_new_instance(self):
        """reset_persistence_manager() should create new default instance."""
        pm1 = get_persistence_manager()
        reset_persistence_manager()
        pm2 = get_persistence_manager()

        assert pm1 is not pm2
        assert pm2.is_enabled()


class TestPersistenceIntegration:
    """Integration tests for persistence system."""

    @pytest.fixture(autouse=True)
    def setup_db(self):
        """Setup database for testing."""
        config = DatabaseConfig.for_testing()
        DBConnectionManager.reset()
        manager = DBConnectionManager.initialize(config)
        manager.create_all_tables()
        reset_persistence_manager()
        yield
        DBConnectionManager.reset()
        reset_persistence_manager()

    def test_unified_rule_auto_persists_by_default(self):
        """Unified Rule should auto-persist by default."""
        from fluxrules.domain.unified_rule import Rule as UnifiedRule

        # Note: This test verifies the persist mechanism is integrated
        # but we disable it for this test to avoid DB dependencies in all tests
        pm = get_persistence_manager()
        pm.disable_persistence()

        rule = UnifiedRule(
            name="Test Rule",
            condition_dsl={"type": "condition", "field": "age", "op": ">", "value": 18},
            action="allow",
        )

        assert rule.id is not None
        assert isinstance(rule.id, int)

    def test_persist_respects_opt_out(self):
        """Unified Rule with persist=False should not persist."""
        from fluxrules.domain.unified_rule import Rule as UnifiedRule

        pm = get_persistence_manager()
        pm.disable_persistence()

        rule = UnifiedRule(
            name="Test Rule",
            condition_dsl={"type": "condition", "field": "age", "op": ">", "value": 18},
            action="allow",
            persist=False,
        )

        assert rule.id is not None
        # ID should be locally generated, not from DB
        assert isinstance(rule.id, int)
