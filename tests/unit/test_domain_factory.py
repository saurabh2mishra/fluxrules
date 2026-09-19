"""Tests for domain factory functions."""

import pytest

from fluxrules.domain.factory import rule_from_dict, ruleset_from_dict
from fluxrules.domain.models import EngineRule, Ruleset


class TestRuleFromDict:
    def test_native_format(self):
        data = {
            "id": 1,
            "name": "test_rule",
            "conditions": [
                {"fact": "age", "operator": "gte", "value": 18},
                {"fact": "income", "operator": "gt", "value": 30000},
            ],
            "actions": ["approve"],
            "priority": 5,
            "enabled": True,
        }
        rule = rule_from_dict(data)
        assert isinstance(rule, EngineRule)
        assert rule.id == 1
        assert rule.name == "test_rule"
        assert len(rule.conditions) == 2
        assert rule.conditions[0].fact == "age"
        assert rule.conditions[0].operator == "gte"
        assert rule.actions == ("approve",)
        assert rule.priority == 5

    def test_dsl_format(self):
        data = {
            "id": 2,
            "name": "dsl_rule",
            "condition_dsl": {
                "type": "condition",
                "field": "amount",
                "op": ">",
                "value": 1000,
            },
            "action": "flag_for_review",
            "priority": 10,
            "enabled": True,
        }
        rule = rule_from_dict(data)
        assert isinstance(rule, EngineRule)
        assert rule.id == 2
        assert rule.conditions[0].fact == "amount"
        assert rule.conditions[0].operator == ">"
        assert rule.actions == ("flag_for_review",)

    def test_dsl_group_format(self):
        data = {
            "id": 3,
            "name": "group_rule",
            "condition_dsl": {
                "type": "group",
                "op": "AND",
                "children": [
                    {"type": "condition", "field": "a", "op": "==", "value": 1},
                    {"type": "condition", "field": "b", "op": ">", "value": 2},
                ],
            },
            "action": "do_something",
        }
        rule = rule_from_dict(data)
        assert len(rule.conditions) == 2
        assert rule.conditions[0].fact == "a"
        assert rule.conditions[1].fact == "b"

    def test_empty_dict_raises(self):
        with pytest.raises(ValueError, match="must contain 'id' and 'name'"):
            rule_from_dict({})

    def test_not_a_dict_raises(self):
        with pytest.raises(ValueError, match="Expected dict"):
            rule_from_dict("not a dict")  # type: ignore[arg-type]

    def test_missing_name_raises(self):
        with pytest.raises(ValueError, match="must contain 'id' and 'name'"):
            rule_from_dict({"id": 1})

    def test_defaults(self):
        data = {"id": 1, "name": "minimal"}
        rule = rule_from_dict(data)
        assert rule.priority == 0
        assert rule.enabled is True
        assert rule.conditions == ()
        assert rule.actions == ()


class TestRulesetFromDict:
    def test_basic(self):
        data = {
            "id": 1,
            "name": "test_set",
            "rules": [
                {
                    "id": 1,
                    "name": "r1",
                    "conditions": [{"fact": "x", "operator": "eq", "value": 1}],
                    "actions": ["act"],
                },
            ],
        }
        rs = ruleset_from_dict(data)
        assert isinstance(rs, Ruleset)
        assert rs.group == "test_set"
        assert len(rs.rules) == 1

    def test_empty_rules(self):
        data = {"group": "empty"}
        rs = ruleset_from_dict(data)
        assert rs.rules == ()

    def test_invalid_raises(self):
        with pytest.raises(ValueError):
            ruleset_from_dict({})
