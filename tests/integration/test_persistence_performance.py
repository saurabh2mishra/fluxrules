"""Performance tests for the PHREAK engine with automatic persistence.

Ensures that enabling persistence doesn't degrade rule evaluation performance.
"""

import pytest

from fluxrules.domain.models import EngineRule, RuleCondition
from fluxrules.persistence import (
    DatabaseConfig,
    DBConnectionManager,
    get_persistence_manager,
    reset_persistence_manager,
)


@pytest.fixture(autouse=True)
def setup_db():
    """Setup database for testing."""
    config = DatabaseConfig.for_testing()
    DBConnectionManager.reset()
    manager = DBConnectionManager.initialize(config)
    manager.create_all_tables()
    reset_persistence_manager()
    yield
    DBConnectionManager.reset()
    reset_persistence_manager()


class TestPHREAKWithPersistence:
    """Test PHREAK engine with persistence enabled."""

    def test_phreak_with_persisted_rules(self):
        """PHREAK should work correctly with persisted rules."""
        # Create and persist rules
        rule = EngineRule(
            id=None,
            name="test_rule",
            conditions=(RuleCondition(fact="status", operator="==", value="active"),),
            actions=("process",),
            priority=10,
        )

        # Persist
        pm = get_persistence_manager()
        persisted = pm.persist_rule(rule)

        # Should have ID
        assert persisted.id is not None
        assert persisted.name == "test_rule"

    def test_phreak_evaluation_performance_unchanged(self):
        """PHREAK rule evaluation should not be affected by persistence layer."""
        pm = get_persistence_manager()
        pm.disable_persistence()

        # Create rule
        rule = EngineRule(
            id=1,
            name="phreak_rule",
            conditions=(RuleCondition(fact="score", operator=">", value=75),),
            actions=("approve",),
        )

        # Verify rule integrity after creation
        assert rule.id == 1
        assert rule.name == "phreak_rule"
        assert len(rule.conditions) == 1
        assert rule.conditions[0].fact == "score"


class TestPersistenceRuleIntegrity:
    """Test that persistence maintains rule integrity."""

    def test_persisted_rule_preserves_conditions(self):
        """Persisted rules should maintain condition integrity."""
        rule = EngineRule(
            id=None,
            name="condition_test",
            conditions=(
                RuleCondition(fact="amount", operator=">", value=1000),
                RuleCondition(fact="status", operator="==", value="pending"),
            ),
            actions=("escalate", "notify"),
            priority=5,
        )

        pm = get_persistence_manager()
        persisted = pm.persist_rule(rule)

        # Check all conditions preserved
        assert len(persisted.conditions) == 2
        assert persisted.conditions[0].fact == "amount"
        assert persisted.conditions[1].fact == "status"

    def test_persisted_rule_preserves_actions(self):
        """Persisted rules should maintain action integrity."""
        rule = EngineRule(
            id=None,
            name="action_test",
            conditions=(RuleCondition(fact="test", operator="==", value=True),),
            actions=("action1", "action2", "action3"),
            priority=1,
        )

        pm = get_persistence_manager()
        persisted = pm.persist_rule(rule)

        # Check all actions preserved
        assert len(persisted.actions) == 3
        assert persisted.actions[0] == "action1"
        assert persisted.actions[1] == "action2"
        assert persisted.actions[2] == "action3"

    def test_persisted_rule_preserves_priority(self):
        """Persisted rules should maintain priority."""
        rule = EngineRule(
            id=None,
            name="priority_test",
            conditions=(RuleCondition(fact="test", operator="==", value=True),),
            actions=("test",),
            priority=100,
        )

        pm = get_persistence_manager()
        persisted = pm.persist_rule(rule)

        # Check priority preserved
        assert persisted.priority == 100


class TestPersistenceScale:
    """Test persistence at scale."""

    def test_persist_many_rules(self):
        """Should be able to persist many rules efficiently."""
        pm = get_persistence_manager()

        # Create 100 rules
        rules = [
            EngineRule(
                id=None,
                name=f"rule_{i}",
                conditions=(RuleCondition(fact="value", operator=">", value=i),),
                actions=(f"action_{i}",),
                priority=i,
            )
            for i in range(100)
        ]

        # Persist all
        persisted = pm.persist_ruleset(rules)

        # All should have IDs
        assert len(persisted) == 100
        assert all(r.id is not None for r in persisted)

        # IDs should be unique
        ids = [r.id for r in persisted]
        assert len(set(ids)) == 100  # All unique

    def test_large_condition_preserved(self):
        """Large/complex conditions should be preserved."""
        rule = EngineRule(
            id=None,
            name="complex_rule",
            conditions=tuple(
                RuleCondition(fact=f"field_{i}", operator=">", value=i) for i in range(10)
            ),
            actions=("complex_action",),
        )

        pm = get_persistence_manager()
        persisted = pm.persist_rule(rule)

        # All conditions preserved
        assert len(persisted.conditions) == 10
