"""Tests for DSL validation."""

import pytest

from fluxrules.domain.dsl.validation import DSLValidationError, validate_dsl


class TestDSLValidation:
    """Tests for strict DSL validation."""

    def test_valid_condition(self):
        dsl = {"type": "condition", "field": "amount", "op": ">", "value": 1000}
        validate_dsl(dsl)  # Should not raise

    def test_valid_group(self):
        dsl = {
            "type": "group",
            "op": "AND",
            "children": [
                {"type": "condition", "field": "age", "op": ">", "value": 18},
                {"type": "condition", "field": "status", "op": "==", "value": "active"},
            ],
        }
        validate_dsl(dsl)

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
        validate_dsl(dsl)

    def test_valid_exists(self):
        dsl = {"type": "exists", "field": "email"}
        validate_dsl(dsl)

    def test_invalid_operator_rejected(self):
        dsl = {"type": "condition", "field": "amount", "op": "gtt", "value": 1000}
        with pytest.raises(DSLValidationError, match="Invalid operator 'gtt'"):
            validate_dsl(dsl)

    def test_unknown_keys_rejected(self):
        dsl = {
            "type": "condition",
            "field": "amount",
            "op": ">",
            "value": 1000,
            "extra_key": "ignored",
        }
        with pytest.raises(DSLValidationError, match="Unknown keys"):
            validate_dsl(dsl)

    def test_typo_in_field_key_rejected(self):
        dsl = {"type": "condition", "fild": "amount", "op": ">", "value": 1000}
        with pytest.raises(DSLValidationError, match="Unknown keys"):
            validate_dsl(dsl)

    def test_missing_field_rejected(self):
        dsl = {"type": "condition", "op": ">", "value": 1000}
        with pytest.raises(DSLValidationError, match="missing required 'field'"):
            validate_dsl(dsl)

    def test_missing_op_rejected(self):
        dsl = {"type": "condition", "field": "amount", "value": 1000}
        with pytest.raises(DSLValidationError, match="missing required 'op'"):
            validate_dsl(dsl)

    def test_missing_value_rejected(self):
        dsl = {"type": "condition", "field": "amount", "op": ">"}
        with pytest.raises(DSLValidationError, match="missing required 'value'"):
            validate_dsl(dsl)

    def test_empty_field_rejected(self):
        dsl = {"type": "condition", "field": "", "op": ">", "value": 1000}
        with pytest.raises(DSLValidationError, match="non-empty string"):
            validate_dsl(dsl)

    def test_unknown_type_rejected(self):
        dsl = {"type": "unknown_node", "field": "x"}
        with pytest.raises(DSLValidationError, match="Unknown DSL node type"):
            validate_dsl(dsl)

    def test_missing_type_rejected(self):
        dsl = {"field": "x", "op": ">", "value": 1}
        with pytest.raises(DSLValidationError, match="missing required 'type'"):
            validate_dsl(dsl)

    def test_non_dict_rejected(self):
        with pytest.raises(DSLValidationError, match="must be a dict"):
            validate_dsl("not a dict")  # type: ignore

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
        with pytest.raises(DSLValidationError, match="Unknown keys"):
            validate_dsl(dsl)

    def test_empty_children_rejected(self):
        dsl = {"type": "group", "op": "AND", "children": []}
        with pytest.raises(DSLValidationError, match="empty 'children'"):
            validate_dsl(dsl)

    def test_invalid_group_op_rejected(self):
        dsl = {
            "type": "group",
            "op": "XOR",
            "children": [{"type": "condition", "field": "x", "op": "==", "value": 1}],
        }
        with pytest.raises(DSLValidationError, match="Invalid group operator"):
            validate_dsl(dsl)

    def test_all_valid_operators_accepted(self):
        from fluxrules.engine.operators import VALID_OPERATORS

        for op in VALID_OPERATORS:
            dsl = {"type": "condition", "field": "x", "op": op, "value": 1}
            validate_dsl(dsl)  # Should not raise
