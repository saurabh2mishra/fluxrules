"""Tests for the RulePersistencePort and InMemoryRulePersistence."""

from fluxrules.domain.models import EngineRule, RuleCondition, Ruleset
from fluxrules.ports.persistence import InMemoryRulePersistence, RulePersistencePort


def _make_rule(id: int, group: str = "test") -> EngineRule:
    return EngineRule(
        id=id,
        name=f"rule_{id}",
        conditions=(RuleCondition(fact="x", operator="==", value=1),),
        actions=("action_1",),
        priority=1,
        group=group,
    )


class TestInMemoryRulePersistence:
    """Tests for the in-memory persistence adapter."""

    def test_implements_port(self):
        assert isinstance(InMemoryRulePersistence(), RulePersistencePort)

    def test_save_and_load_rule(self):
        store = InMemoryRulePersistence()
        rule = _make_rule(1)
        rid = store.save_rule(rule)
        loaded = store.load_rule(rid)
        assert loaded is not None
        assert loaded.name == "rule_1"

    def test_load_nonexistent_returns_none(self):
        store = InMemoryRulePersistence()
        assert store.load_rule(999) is None

    def test_delete_rule(self):
        store = InMemoryRulePersistence()
        rule = _make_rule(1)
        rid = store.save_rule(rule)
        assert store.delete_rule(rid) is True
        assert store.load_rule(rid) is None

    def test_delete_nonexistent_returns_false(self):
        store = InMemoryRulePersistence()
        assert store.delete_rule(999) is False

    def test_load_all_rules(self):
        store = InMemoryRulePersistence()
        store.save_rule(_make_rule(1))
        store.save_rule(_make_rule(2))
        assert len(store.load_all_rules()) == 2

    def test_save_and_load_ruleset(self):
        store = InMemoryRulePersistence()
        rs = Ruleset(
            group="test_group",
            rules=(_make_rule(1, "test_group"), _make_rule(2, "test_group")),
        )
        ids = store.save_ruleset(rs)
        assert len(ids) == 2

    def test_load_all_rulesets(self):
        store = InMemoryRulePersistence()
        store.save_rule(_make_rule(1, "group_a"))
        store.save_rule(_make_rule(2, "group_b"))
        rulesets = store.load_all_rulesets()
        assert len(rulesets) == 2
