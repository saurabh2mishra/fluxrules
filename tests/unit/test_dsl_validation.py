"""Tests for DSL validation."""

import pytest

from fluxrules.domain.conditions.validation import ConditionValidationError, validate_conditions


class TestDSLValidation:
    """Tests for strict DSL validation."""

    def test_valid_condition(self):
        dsl = {"type": "condition", "field": "amount", "op": ">", "value": 1000}
        validate_conditions(dsl)  # Should not raise

    def test_valid_group(self):
        dsl = {
            "type": "group",
            "op": "AND",
            "children": [
                {"type": "condition", "field": "age", "op": ">", "value": 18},
                {"type": "condition", "field": "status", "op": "==", "value": "active"},
            ],
        }
        validate_conditions(dsl)

    def test_valid_not(self):
        dsl = {
            "type": "not",
            "condition": {
                "type": "condition",
                "field": "blocked",
                "op": "==",
                "value": True,
            },
        }
        validate_conditions(dsl)

    def test_valid_exists(self):
        dsl = {"type": "exists", "field": "email"}
        validate_conditions(dsl)

    def test_invalid_operator_rejected(self):
        dsl = {"type": "condition", "field": "amount", "op": "gtt", "value": 1000}
        with pytest.raises(ConditionValidationError, match="Invalid operator 'gtt'"):
            validate_conditions(dsl)

    def test_unknown_keys_rejected(self):
        dsl = {
            "type": "condition",
            "field": "amount",
            "op": ">",
            "value": 1000,
            "extra_key": "ignored",
        }
        with pytest.raises(ConditionValidationError, match="Unknown keys"):
            validate_conditions(dsl)

    def test_typo_in_field_key_rejected(self):
        dsl = {"type": "condition", "fild": "amount", "op": ">", "value": 1000}
        with pytest.raises(ConditionValidationError, match="Unknown keys"):
            validate_conditions(dsl)

    def test_missing_field_rejected(self):
        dsl = {"type": "condition", "op": ">", "value": 1000}
        with pytest.raises(ConditionValidationError, match="missing required 'field'"):
            validate_conditions(dsl)

    def test_missing_op_rejected(self):
        dsl = {"type": "condition", "field": "amount", "value": 1000}
        with pytest.raises(ConditionValidationError, match="missing required 'op'"):
            validate_conditions(dsl)

    def test_missing_value_rejected(self):
        dsl = {"type": "condition", "field": "amount", "op": ">"}
        with pytest.raises(ConditionValidationError, match="missing required 'value'"):
            validate_conditions(dsl)

    def test_empty_field_rejected(self):
        dsl = {"type": "condition", "field": "", "op": ">", "value": 1000}
        with pytest.raises(ConditionValidationError, match="non-empty string"):
            validate_conditions(dsl)

    def test_unknown_type_rejected(self):
        dsl = {"type": "unknown_node", "field": "x"}
        with pytest.raises(ConditionValidationError, match="Unknown DSL node type"):
            validate_conditions(dsl)

    def test_missing_type_rejected(self):
        dsl = {"field": "x", "op": ">", "value": 1}
        with pytest.raises(ConditionValidationError, match="missing required 'type'"):
            validate_conditions(dsl)

    def test_non_dict_rejected(self):
        with pytest.raises(ConditionValidationError, match="must be a dict"):
            validate_conditions("not a dict")  # type: ignore

    def test_nested_invalid_child_in_group(self):
        dsl = {
            "type": "group",
            "op": "AND",
            "children": [
                {"type": "condition", "field": "age", "op": ">", "value": 18},
                {
                    "type": "condition",
                    "fild": "amount",
                    "op": ">",
                    "value": 1000,
                },  # typo
            ],
        }
        with pytest.raises(ConditionValidationError, match="Unknown keys"):
            validate_conditions(dsl)

    def test_empty_children_rejected(self):
        dsl = {"type": "group", "op": "AND", "children": []}
        with pytest.raises(ConditionValidationError, match="empty 'children'"):
            validate_conditions(dsl)

    def test_invalid_group_op_rejected(self):
        dsl = {
            "type": "group",
            "op": "XOR",
            "children": [{"type": "condition", "field": "x", "op": "==", "value": 1}],
        }
        with pytest.raises(ConditionValidationError, match="Invalid group operator"):
            validate_conditions(dsl)

    def test_all_valid_operators_accepted(self):
        from fluxrules.engine.operators import VALID_OPERATORS

        for op in VALID_OPERATORS:
            dsl = {"type": "condition", "field": "x", "op": op, "value": 1}
            validate_conditions(dsl)  # Should not raise


class TestGroupValidationExtended:
    def test_group_missing_op_rejected(self):
        with pytest.raises(ConditionValidationError, match="missing required 'op'"):
            validate_conditions(
                {
                    "type": "group",
                    "children": [{"type": "condition", "field": "x", "op": ">", "value": 1}],
                }
            )

    def test_composite_missing_op_rejected(self):
        with pytest.raises(ConditionValidationError, match="missing required 'op'"):
            validate_conditions(
                {
                    "type": "composite",
                    "children": [{"type": "condition", "field": "x", "op": ">", "value": 1}],
                }
            )

    def test_group_missing_children_key_rejected(self):
        with pytest.raises(ConditionValidationError, match="missing required 'children'"):
            validate_conditions({"type": "group", "op": "AND"})

    def test_group_children_not_list_rejected(self):
        with pytest.raises(ConditionValidationError, match="must be a list"):
            validate_conditions({"type": "group", "op": "AND", "children": "not-a-list"})

    def test_and_type_accepts_no_op_field(self):
        dsl = {
            "type": "and",
            "conditions": [{"type": "condition", "field": "x", "op": ">", "value": 1}],
        }
        validate_conditions(dsl)  # op not required for 'and' shorthand type

    def test_group_with_conditions_key(self):
        dsl = {
            "type": "group",
            "op": "OR",
            "conditions": [{"type": "condition", "field": "x", "op": ">", "value": 1}],
        }
        validate_conditions(dsl)  # 'conditions' accepted as alias for 'children'


class TestNotValidationExtended:
    def test_not_with_children_list(self):
        dsl = {
            "type": "not",
            "children": [
                {"type": "condition", "field": "blocked", "op": "==", "value": True},
            ],
        }
        validate_conditions(dsl)

    def test_not_with_conditions_list(self):
        dsl = {
            "type": "not",
            "conditions": [
                {"type": "condition", "field": "blocked", "op": "==", "value": True},
            ],
        }
        validate_conditions(dsl)

    def test_not_empty_rejected(self):
        with pytest.raises(ConditionValidationError, match="missing child"):
            validate_conditions({"type": "not"})


class TestExistsValidationExtended:
    def test_exists_missing_field_rejected(self):
        with pytest.raises(ConditionValidationError, match="missing required 'field'"):
            validate_conditions({"type": "exists"})

    def test_exists_empty_field_rejected(self):
        with pytest.raises(ConditionValidationError, match="non-empty string"):
            validate_conditions({"type": "exists", "field": ""})

    def test_exists_valid(self):
        validate_conditions({"type": "exists", "field": "email"})


class TestSequenceValidation:
    def test_valid_sequence(self):
        dsl = {
            "type": "sequence",
            "steps": [
                {"type": "condition", "field": "a", "op": ">", "value": 1},
                {"type": "condition", "field": "b", "op": ">", "value": 2},
            ],
        }
        validate_conditions(dsl)

    def test_sequence_missing_steps_rejected(self):
        with pytest.raises(ConditionValidationError, match="missing required 'steps'"):
            validate_conditions({"type": "sequence"})

    def test_sequence_empty_steps_rejected(self):
        with pytest.raises(ConditionValidationError, match="non-empty list"):
            validate_conditions({"type": "sequence", "steps": []})

    def test_sequence_invalid_step_rejected(self):
        with pytest.raises(ConditionValidationError):
            validate_conditions(
                {
                    "type": "sequence",
                    "steps": [{"type": "bad_type", "field": "x"}],
                }
            )


class TestAccumulateValidation:
    def test_valid_accumulate(self):
        dsl = {
            "type": "accumulate",
            "field": "amount",
            "function": "sum",
        }
        validate_conditions(dsl)

    def test_accumulate_missing_function_rejected(self):
        with pytest.raises(ConditionValidationError, match="missing required 'function'"):
            validate_conditions({"type": "accumulate", "field": "amount"})

    def test_accumulate_invalid_function_rejected(self):
        with pytest.raises(ConditionValidationError, match="Invalid accumulate function"):
            validate_conditions({"type": "accumulate", "field": "x", "function": "median"})
