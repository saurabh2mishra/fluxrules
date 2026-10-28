"""Unit tests for API serialization helpers that use the renamed 'conditions' field.

These are pure-function tests — no database, no HTTP client. They pin the
condition_dsl → conditions rename contract so a future rename can't silently
slip through without a test failure.
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock


def _orm_rule(conditions, **kwargs):
    """Minimal ORM-like object with a .conditions attribute."""
    rule = MagicMock()
    rule.conditions = conditions
    rule.id = kwargs.get("id", 1)
    rule.name = kwargs.get("name", "r")
    rule.description = kwargs.get("description", None)
    rule.group = kwargs.get("group", "default")
    rule.priority = kwargs.get("priority", 0)
    rule.enabled = kwargs.get("enabled", True)
    rule.action = kwargs.get("action", "log")
    rule.rule_metadata = kwargs.get("rule_metadata", None)
    rule.evaluation_mode = kwargs.get("evaluation_mode", None)
    rule.current_version = kwargs.get("current_version", 1)
    rule.created_at = kwargs.get("created_at", None)
    rule.updated_at = kwargs.get("updated_at", None)
    rule.created_by = kwargs.get("created_by", None)
    return rule


class TestSerializeRule:
    """serialize_rule() must use the 'conditions' key and handle both str and dict."""

    def _call(self, rule):
        from fluxrules.api.routes.rules import serialize_rule

        return serialize_rule(rule)

    def test_conditions_dict_passed_through(self):
        cond = {"type": "condition", "field": "amount", "op": ">", "value": 100}
        result = self._call(_orm_rule(conditions=cond))
        assert result["conditions"] == cond

    def test_conditions_json_string_is_decoded(self):
        cond = {"type": "condition", "field": "score", "op": ">=", "value": 50}
        result = self._call(_orm_rule(conditions=json.dumps(cond)))
        assert result["conditions"] == cond

    def test_output_uses_conditions_key_not_condition_dsl(self):
        result = self._call(_orm_rule(conditions={"type": "exists", "field": "email"}))
        assert "conditions" in result
        assert "condition_dsl" not in result

    def test_rule_metadata_none_passes_through(self):
        result = self._call(
            _orm_rule(conditions={"type": "exists", "field": "x"}, rule_metadata=None)
        )
        assert result["rule_metadata"] is None

    def test_rule_metadata_string_is_decoded(self):
        meta = {"source": "manual"}
        result = self._call(
            _orm_rule(conditions={"type": "exists", "field": "x"}, rule_metadata=json.dumps(meta))
        )
        assert result["rule_metadata"] == meta


class TestRuleToPayload:
    """_rule_to_payload() must use the 'conditions' key and handle str/dict."""

    def _call(self, rule):
        from fluxrules.api.services.rule_validation_service import RuleValidationService

        return RuleValidationService._rule_to_payload(rule)

    def test_conditions_dict_passed_through(self):
        cond = {"type": "condition", "field": "age", "op": ">", "value": 18}
        result = self._call(_orm_rule(conditions=cond))
        assert result["conditions"] == cond

    def test_conditions_json_string_is_decoded(self):
        cond = {"type": "condition", "field": "tier", "op": "==", "value": "gold"}
        result = self._call(_orm_rule(conditions=json.dumps(cond)))
        assert result["conditions"] == cond

    def test_output_uses_conditions_key_not_condition_dsl(self):
        result = self._call(_orm_rule(conditions={"type": "exists", "field": "id"}))
        assert "conditions" in result
        assert "condition_dsl" not in result

    def test_id_is_stringified(self):
        result = self._call(_orm_rule(conditions={"type": "exists", "field": "x"}, id=42))
        assert result["id"] == "42"


class TestDetectAllConflicts:
    """_detect_all_conflicts reads 'conditions' key from rule dicts."""

    def test_no_conflicts_empty_db(self):
        from unittest.mock import patch

        from fluxrules.api.routes.rules import _detect_all_conflicts

        with patch("fluxrules.api.routes.rules.RuleCache") as MockCache:
            MockCache.return_value.get_rules.return_value = []
            result = _detect_all_conflicts(MagicMock())

        assert result == {"conflicts": []}

    def test_duplicate_conditions_detected(self):
        from unittest.mock import patch

        from fluxrules.api.routes.rules import _detect_all_conflicts

        cond = {"type": "condition", "field": "x", "op": ">", "value": 1}
        rules = [
            {"id": 1, "name": "A", "conditions": cond, "group": "g", "priority": 0},
            {"id": 2, "name": "B", "conditions": cond, "group": "g", "priority": 1},
        ]
        with patch("fluxrules.api.routes.rules.RuleCache") as MockCache:
            MockCache.return_value.get_rules.return_value = rules
            result = _detect_all_conflicts(MagicMock())

        dupe_conflicts = [c for c in result["conflicts"] if c["type"] == "duplicate_condition"]
        assert len(dupe_conflicts) == 1
        assert dupe_conflicts[0]["rule1_id"] == 1
        assert dupe_conflicts[0]["rule2_id"] == 2
