"""Tests for the F / Field operator-overloading DSL."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from fluxrules import F, Field, Rule, evaluate
from fluxrules.domain.field import Condition


# ---------------------------------------------------------------------------
# Field construction
# ---------------------------------------------------------------------------


class TestFieldConstruction:
    def test_f_is_alias_for_field(self):
        assert F is Field

    def test_repr(self):
        assert repr(F("amount")) == "F('amount')"

    def test_empty_name_raises(self):
        with pytest.raises(ValueError):
            F("")

    def test_non_string_name_raises(self):
        with pytest.raises(ValueError):
            F(None)  # type: ignore[arg-type]

    def test_field_is_unhashable(self):
        """Field.__eq__ returns Condition, so Field must not be hashable."""
        with pytest.raises(TypeError):
            {F("x")}


# ---------------------------------------------------------------------------
# Leaf condition dicts - comparison operators
# ---------------------------------------------------------------------------


class TestComparisonOperators:
    def test_gt(self):
        assert F("amount").__gt__(10000).to_dict() == {
            "type": "condition",
            "field": "amount",
            "op": ">",
            "value": 10000,
        }

    def test_ge(self):
        c = (F("age") >= 18).to_dict()
        assert c == {"type": "condition", "field": "age", "op": ">=", "value": 18}

    def test_lt(self):
        c = (F("score") < 50).to_dict()
        assert c == {"type": "condition", "field": "score", "op": "<", "value": 50}

    def test_le(self):
        c = (F("score") <= 100).to_dict()
        assert c == {"type": "condition", "field": "score", "op": "<=", "value": 100}

    def test_eq(self):
        c = (F("country") == "US").to_dict()
        assert c == {"type": "condition", "field": "country", "op": "==", "value": "US"}

    def test_ne(self):
        c = (F("status") != "blocked").to_dict()
        assert c == {"type": "condition", "field": "status", "op": "!=", "value": "blocked"}

    def test_value_can_be_string(self):
        c = (F("name") == "Alice").to_dict()
        assert c["value"] == "Alice"

    def test_value_can_be_float(self):
        c = (F("ratio") > 0.5).to_dict()
        assert c["value"] == 0.5

    def test_value_can_be_bool(self):
        c = (F("active") == True).to_dict()  # noqa: E712
        assert c["value"] is True


# ---------------------------------------------------------------------------
# Named method operators
# ---------------------------------------------------------------------------


class TestNamedOperators:
    def test_in_(self):
        c = F("status").isin(["active", "pending"]).to_dict()
        assert c == {
            "type": "condition",
            "field": "status",
            "op": "in",
            "value": ["active", "pending"],
        }

    def test_not_in(self):
        c = F("country").not_in(["CN", "RU"]).to_dict()
        assert c["op"] == "not_in"
        assert c["value"] == ["CN", "RU"]

    def test_contains(self):
        c = F("tags").contains("fraud").to_dict()
        assert c["op"] == "contains"
        assert c["value"] == "fraud"

    def test_not_contains(self):
        c = F("tags").not_contains("vip").to_dict()
        assert c["op"] == "not_contains"

    def test_starts_with(self):
        c = F("email").starts_with("admin@").to_dict()
        assert c["op"] == "starts_with"
        assert c["value"] == "admin@"

    def test_ends_with(self):
        c = F("email").ends_with(".gov").to_dict()
        assert c["op"] == "ends_with"

    def test_regex(self):
        c = F("phone").regex(r"^\+1\d{10}$").to_dict()
        assert c["op"] == "regex"
        assert c["value"] == r"^\+1\d{10}$"

    def test_exists(self):
        c = F("email").exists().to_dict()
        assert c == {"type": "exists", "field": "email"}


# ---------------------------------------------------------------------------
# Boolean composition
# ---------------------------------------------------------------------------


class TestBooleanComposition:
    def test_and_produces_group(self):
        c = ((F("amount") > 10000) & (F("country") == "US")).to_dict()
        assert c["type"] == "group"
        assert c["op"] == "AND"
        assert len(c["children"]) == 2
        assert c["children"][0] == {"type": "condition", "field": "amount", "op": ">", "value": 10000}
        assert c["children"][1] == {"type": "condition", "field": "country", "op": "==", "value": "US"}

    def test_or_produces_group(self):
        c = ((F("amount") > 10000) | (F("country") == "US")).to_dict()
        assert c["type"] == "group"
        assert c["op"] == "OR"
        assert len(c["children"]) == 2

    def test_invert_produces_not(self):
        c = (~(F("blocked") == True)).to_dict()  # noqa: E712
        assert c["type"] == "not"
        assert "condition" in c
        assert c["condition"]["field"] == "blocked"

    def test_chained_and(self):
        c = ((F("a") > 1) & (F("b") == "x") & (F("c") < 5)).to_dict()
        # (a & b) & c → AND(AND(a,b), c)  - nested AND is valid
        assert c["type"] == "group"
        assert c["op"] == "AND"

    def test_mixed_and_or(self):
        c = ((F("a") > 1) & ((F("b") == "x") | (F("c") < 5))).to_dict()
        assert c["type"] == "group"
        assert c["op"] == "AND"
        or_child = c["children"][1]
        assert or_child["type"] == "group"
        assert or_child["op"] == "OR"

    def test_not_of_group(self):
        group = (F("a") > 1) & (F("b") == "x")
        c = (~group).to_dict()
        assert c["type"] == "not"
        inner = c["condition"]
        assert inner["type"] == "group"
        assert inner["op"] == "AND"

    def test_condition_repr(self):
        c = F("x") > 1
        assert "Condition" in repr(c)


# ---------------------------------------------------------------------------
# Integration with Rule
# ---------------------------------------------------------------------------


class TestRuleIntegration:
    def test_single_condition_accepted(self):
        rule = Rule(
            name="age check",
            conditions=F("age") >= 18,
            action="allow",
        )
        assert rule.conditions == {"type": "condition", "field": "age", "op": ">=", "value": 18}

    def test_and_group_accepted(self):
        rule = Rule(
            name="high value US",
            conditions=(F("amount") > 10000) & (F("country") == "US"),
            action="flag",
        )
        assert rule.conditions["type"] == "group"
        assert rule.conditions["op"] == "AND"
        assert len(rule.conditions["children"]) == 2

    def test_or_group_accepted(self):
        rule = Rule(
            name="either condition",
            conditions=(F("amount") > 50000) | (F("risk") == "high"),
            action="review",
        )
        assert rule.conditions["op"] == "OR"

    def test_not_condition_accepted(self):
        rule = Rule(
            name="not blocked",
            conditions=~(F("blocked") == True),  # noqa: E712
            action="allow",
        )
        assert rule.conditions["type"] == "not"

    def test_exists_accepted(self):
        rule = Rule(
            name="has email",
            conditions=F("email").exists(),
            action="send",
        )
        assert rule.conditions == {"type": "exists", "field": "email"}

    def test_named_operator_accepted(self):
        rule = Rule(
            name="active status",
            conditions=F("status").isin(["active", "trial"]),
            action="allow",
        )
        assert rule.conditions["op"] == "in"

    def test_invalid_operator_rejected(self):
        """Validation still rejects unknown operators even when built via F."""
        from fluxrules.domain.field import Condition

        bad = Condition({"type": "condition", "field": "x", "op": "bad_op", "value": 1})
        with pytest.raises(ValidationError, match="Invalid operator"):
            Rule(name="bad", conditions=bad)

    def test_raw_dict_still_works(self):
        """Existing dict-based authoring is unaffected."""
        rule = Rule(
            name="raw",
            conditions={"type": "condition", "field": "amount", "op": ">", "value": 100},
            action="flag",
        )
        assert rule.conditions["field"] == "amount"

    def test_model_dump_round_trip(self):
        """Rule built with F round-trips through model_dump without losing structure."""
        original_cond = (F("amount") > 10000) & (F("country") == "US")
        rule = Rule(name="rt", conditions=original_cond, action="flag")
        data = rule.model_dump()
        restored = Rule(**data)
        assert restored.conditions == rule.conditions

    def test_conditions_stored_as_plain_dict(self):
        """After coercion, Rule.conditions is a plain dict, not a Condition."""
        rule = Rule(name="plain", conditions=F("x") > 1)
        assert isinstance(rule.conditions, dict)
        assert not isinstance(rule.conditions, Condition)


# ---------------------------------------------------------------------------
# Engine evaluation end-to-end
# ---------------------------------------------------------------------------


class TestEndToEnd:
    def test_simple_match(self):
        rule = Rule(name="adult", conditions=F("age") >= 18, action="allow")
        result = evaluate(rule, {"age": 25})
        assert rule.id in result.fired_rules

    def test_simple_no_match(self):
        rule = Rule(name="adult", conditions=F("age") >= 18, action="allow")
        result = evaluate(rule, {"age": 16})
        assert result.fired_rules == []

    def test_and_group_match(self):
        rule = Rule(
            name="hv_us",
            conditions=(F("amount") > 10000) & (F("country") == "US"),
            action="flag",
        )
        assert rule.id in evaluate(rule, {"amount": 50000, "country": "US"}).fired_rules
        assert evaluate(rule, {"amount": 50000, "country": "UK"}).fired_rules == []

    def test_or_group_match(self):
        rule = Rule(
            name="either",
            conditions=(F("amount") > 50000) | (F("risk") == "high"),
            action="review",
        )
        assert rule.id in evaluate(rule, {"amount": 10000, "risk": "high"}).fired_rules
        assert rule.id in evaluate(rule, {"amount": 100000, "risk": "low"}).fired_rules
        assert evaluate(rule, {"amount": 100, "risk": "low"}).fired_rules == []

    def test_not_match(self):
        rule = Rule(
            name="not_blocked",
            conditions=~(F("blocked") == True),  # noqa: E712
            action="allow",
        )
        assert rule.id in evaluate(rule, {"blocked": False}).fired_rules
        assert evaluate(rule, {"blocked": True}).fired_rules == []

    def test_exists_match(self):
        rule = Rule(name="has_email", conditions=F("email").exists(), action="send")
        assert rule.id in evaluate(rule, {"email": "a@b.com"}).fired_rules
        assert evaluate(rule, {"name": "Alice"}).fired_rules == []

    def test_in_operator_match(self):
        rule = Rule(
            name="active",
            conditions=F("status").isin(["active", "trial"]),
            action="allow",
        )
        assert rule.id in evaluate(rule, {"status": "active"}).fired_rules
        assert evaluate(rule, {"status": "suspended"}).fired_rules == []
