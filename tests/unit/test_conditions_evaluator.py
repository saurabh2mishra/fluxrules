"""Tests for the conditions tree evaluator."""

import pytest

from fluxrules.domain.conditions.evaluator import (
    LossyConditionRebuildError,
    UnsupportedConditionTreeNodeError,
    conditions_to_tree,
    evaluate_conditions,
    has_logic,
)


def _leaf(field="amount", op=">", value=100):
    return {"type": "condition", "field": field, "op": op, "value": value}


class TestEvaluateConditions:
    def test_condition_leaf_match(self):
        assert evaluate_conditions(_leaf("x", ">", 5), {"x": 10}) is True

    def test_condition_leaf_no_match(self):
        assert evaluate_conditions(_leaf("x", ">", 5), {"x": 3}) is False

    def test_condition_missing_field_returns_false(self):
        assert evaluate_conditions(_leaf("missing", ">", 0), {}) is False

    def test_and_group_all_true(self):
        dsl = {"type": "and", "conditions": [_leaf("a", ">", 0), _leaf("b", ">", 0)]}
        assert evaluate_conditions(dsl, {"a": 1, "b": 1}) is True

    def test_and_group_one_false(self):
        dsl = {"type": "and", "conditions": [_leaf("a", ">", 0), _leaf("b", ">", 0)]}
        assert evaluate_conditions(dsl, {"a": 1, "b": -1}) is False

    def test_or_group_one_true(self):
        dsl = {"type": "or", "conditions": [_leaf("a", ">", 0), _leaf("b", ">", 0)]}
        assert evaluate_conditions(dsl, {"a": -1, "b": 1}) is True

    def test_group_composite_with_logic_key(self):
        dsl = {
            "type": "group",
            "logic": "AND",
            "children": [_leaf("a", ">", 0), _leaf("b", ">", 0)],
        }
        assert evaluate_conditions(dsl, {"a": 1, "b": 1}) is True

    def test_not_with_singular_condition(self):
        dsl = {"type": "not", "condition": _leaf("blocked", "==", True)}
        assert evaluate_conditions(dsl, {"blocked": False}) is True
        assert evaluate_conditions(dsl, {"blocked": True}) is False

    def test_not_with_children_list(self):
        dsl = {"type": "not", "children": [_leaf("blocked", "==", True)]}
        assert evaluate_conditions(dsl, {"blocked": False}) is True
        assert evaluate_conditions(dsl, {"blocked": True}) is False

    def test_not_empty_returns_false(self):
        assert evaluate_conditions({"type": "not"}, {}) is False

    def test_exists_with_field_present(self):
        assert evaluate_conditions({"type": "exists", "field": "email"}, {"email": "a@b.com"}) is True

    def test_exists_with_field_absent(self):
        assert evaluate_conditions({"type": "exists", "field": "email"}, {}) is False

    def test_exists_with_field_none(self):
        assert evaluate_conditions({"type": "exists", "field": "email"}, {"email": None}) is False

    def test_exists_with_inner_condition(self):
        dsl = {"type": "exists", "condition": _leaf("score", ">", 50)}
        assert evaluate_conditions(dsl, {"score": 80}) is True
        assert evaluate_conditions(dsl, {"score": 20}) is False

    def test_exists_no_field_no_condition_returns_false(self):
        assert evaluate_conditions({"type": "exists"}, {}) is False

    def test_stateful_sequence_raises(self):
        with pytest.raises(UnsupportedConditionTreeNodeError, match="working memory"):
            evaluate_conditions({"type": "sequence", "steps": []}, {})

    def test_stateful_accumulate_raises(self):
        with pytest.raises(UnsupportedConditionTreeNodeError, match="working memory"):
            evaluate_conditions({"type": "accumulate", "field": "x", "function": "sum"}, {})

    def test_unknown_type_raises(self):
        with pytest.raises(UnsupportedConditionTreeNodeError, match="Unknown DSL node type"):
            evaluate_conditions({"type": "temporal_window", "condition": {}}, {})

    def test_empty_dict_returns_false(self):
        assert evaluate_conditions({}, {}) is False

    def test_non_dict_returns_false(self):
        assert evaluate_conditions(None, {}) is False  # type: ignore


class TestHasLogic:
    def test_condition_leaf(self):
        assert has_logic(_leaf()) is True

    def test_empty_dict_is_false(self):
        assert has_logic({}) is False

    def test_and_with_children(self):
        assert has_logic({"type": "and", "conditions": [_leaf()]}) is True

    def test_and_no_children_is_false(self):
        assert has_logic({"type": "and", "conditions": []}) is False

    def test_not_with_condition(self):
        assert has_logic({"type": "not", "condition": _leaf()}) is True

    def test_exists_with_field(self):
        assert has_logic({"type": "exists", "field": "x"}) is True

    def test_list_of_conditions(self):
        assert has_logic([_leaf("a"), _leaf("b")]) is True

    def test_list_empty(self):
        assert has_logic([]) is False

    def test_stateful_node_without_children_truthy(self):
        # accumulate / sequence carry logic in their own fields — treated as meaningful
        assert has_logic({"type": "accumulate", "field": "x", "function": "sum"}) is True


class TestConditionsToTree:
    def test_single_condition(self):
        class Cond:
            fact = "amount"
            operator = ">"
            value = 100

        result = conditions_to_tree([Cond()])
        assert result == {"type": "condition", "field": "amount", "op": ">", "value": 100}

    def test_multiple_conditions_become_and_group(self):
        class Cond:
            def __init__(self, field, value):
                self.fact = field
                self.operator = ">"
                self.value = value

        result = conditions_to_tree([Cond("a", 1), Cond("b", 2)])
        assert result["type"] == "and"
        assert len(result["children"]) == 2

    def test_lossy_view_raises(self):
        class LossyView:
            lossy = True

        with pytest.raises(LossyConditionRebuildError):
            conditions_to_tree(LossyView())
