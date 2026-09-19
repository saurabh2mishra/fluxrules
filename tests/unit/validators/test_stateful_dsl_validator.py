"""Tests for StatefulDSLValidator."""

from fluxrules.services.validators.stateful_dsl_validator import StatefulDSLValidator


class TestStatefulDSLValidator:
    """Test suite for StatefulDSLValidator."""

    def setup_method(self):
        """Setup test fixtures."""
        self.validator = StatefulDSLValidator()

    def test_valid_sequence_with_two_steps(self):
        """Sequence with 2+ different steps should be valid."""
        rule_data = {
            "condition_dsl": {
                "type": "sequence",
                "steps": [
                    {
                        "type": "condition",
                        "field": "login_failed",
                        "op": "==",
                        "value": True,
                    },
                    {
                        "type": "condition",
                        "field": "account_locked",
                        "op": "==",
                        "value": True,
                    },
                ],
            }
        }
        result = self.validator.validate(rule_data)
        assert not result.has_errors()

    def test_sequence_missing_steps_field(self):
        """Sequence without 'steps' field should error."""
        rule_data = {
            "condition_dsl": {
                "type": "sequence",
            }
        }
        result = self.validator.validate(rule_data)
        assert result.has_errors()
        errors = result.get_errors()
        assert any("steps" in e.message for e in errors)

    def test_sequence_steps_not_array(self):
        """Sequence with non-array 'steps' should error."""
        rule_data = {
            "condition_dsl": {
                "type": "sequence",
                "steps": "not_an_array",
            }
        }
        result = self.validator.validate(rule_data)
        assert result.has_errors()
        errors = result.get_errors()
        assert any("array" in e.message for e in errors)

    def test_sequence_insufficient_steps(self):
        """Sequence with < 2 steps should error."""
        rule_data = {
            "condition_dsl": {
                "type": "sequence",
                "steps": [
                    {"type": "condition", "field": "event", "op": "==", "value": True},
                ],
            }
        }
        result = self.validator.validate(rule_data)
        assert result.has_errors()
        errors = result.get_errors()
        assert any("minimum" in e.message.lower() for e in errors)

    def test_sequence_identical_steps_warning(self):
        """Sequence with identical repeated steps should warn (suggests count_threshold)."""
        repeated_step = {
            "type": "condition",
            "field": "event",
            "op": "==",
            "value": True,
        }
        rule_data = {
            "condition_dsl": {
                "type": "sequence",
                "steps": [repeated_step, repeated_step, repeated_step],
            }
        }
        result = self.validator.validate(rule_data)
        # Should warn but not error
        assert not result.has_errors()
        assert result.has_warnings()
        warnings = result.get_warnings()
        assert any("count-threshold" in e.message.lower() for e in warnings)

    def test_valid_cross_fact_join(self):
        """Valid cross_fact_join with 2+ facts should be valid."""
        rule_data = {
            "condition_dsl": {
                "type": "cross_fact_join",
                "facts": [
                    {"type": "condition", "field": "user_id", "op": "==", "value": 123},
                    {
                        "type": "condition",
                        "field": "transaction_id",
                        "op": "==",
                        "value": 456,
                    },
                ],
            }
        }
        result = self.validator.validate(rule_data)
        assert not result.has_errors()

    def test_cross_fact_join_missing_facts(self):
        """cross_fact_join without 'facts' field should error."""
        rule_data = {
            "condition_dsl": {
                "type": "cross_fact_join",
            }
        }
        result = self.validator.validate(rule_data)
        assert result.has_errors()
        errors = result.get_errors()
        assert any("facts" in e.message for e in errors)

    def test_cross_fact_join_insufficient_facts(self):
        """cross_fact_join with < 2 facts should error."""
        rule_data = {
            "condition_dsl": {
                "type": "cross_fact_join",
                "facts": [
                    {"type": "condition", "field": "user_id", "op": "==", "value": 123},
                ],
            }
        }
        result = self.validator.validate(rule_data)
        assert result.has_errors()
        errors = result.get_errors()
        assert any("minimum" in e.message.lower() for e in errors)

    def test_valid_count_threshold(self):
        """Valid count_threshold with positive integer threshold should be valid."""
        rule_data = {
            "condition_dsl": {
                "type": "count_threshold",
                "threshold": 5,
                "pattern": {
                    "type": "condition",
                    "field": "event",
                    "op": "==",
                    "value": True,
                },
            }
        }
        result = self.validator.validate(rule_data)
        assert not result.has_errors()

    def test_count_threshold_missing_threshold(self):
        """count_threshold without 'threshold' field should error."""
        rule_data = {
            "condition_dsl": {
                "type": "count_threshold",
                "pattern": {
                    "type": "condition",
                    "field": "event",
                    "op": "==",
                    "value": True,
                },
            }
        }
        result = self.validator.validate(rule_data)
        assert result.has_errors()
        errors = result.get_errors()
        assert any("threshold" in e.message for e in errors)

    def test_count_threshold_invalid_threshold(self):
        """count_threshold with invalid threshold should error."""
        rule_data = {
            "condition_dsl": {
                "type": "count_threshold",
                "threshold": 0,  # Invalid: must be >= 1
                "pattern": {
                    "type": "condition",
                    "field": "event",
                    "op": "==",
                    "value": True,
                },
            }
        }
        result = self.validator.validate(rule_data)
        assert result.has_errors()
        errors = result.get_errors()
        assert any("positive" in e.message.lower() for e in errors)

    def test_top_level_stateful_exclusivity_sequence_and_cross_fact(self):
        """Top-level group can't mix sequence and cross_fact_join."""
        rule_data = {
            "condition_dsl": {
                "type": "group",
                "op": "AND",
                "children": [
                    {
                        "type": "sequence",
                        "steps": [
                            {"type": "condition", "field": "a", "op": "==", "value": 1},
                            {"type": "condition", "field": "b", "op": "==", "value": 2},
                        ],
                    },
                    {
                        "type": "cross_fact_join",
                        "facts": [
                            {"type": "condition", "field": "c", "op": "==", "value": 3},
                            {"type": "condition", "field": "d", "op": "==", "value": 4},
                        ],
                    },
                ],
            }
        }
        result = self.validator.validate(rule_data)
        assert result.has_errors()
        errors = result.get_errors()
        assert any("mutually exclusive" in e.message for e in errors)

    def test_top_level_sequence_only(self):
        """Top-level sequence only should be valid."""
        rule_data = {
            "condition_dsl": {
                "type": "sequence",
                "steps": [
                    {"type": "condition", "field": "a", "op": "==", "value": 1},
                    {"type": "condition", "field": "b", "op": "==", "value": 2},
                ],
            }
        }
        result = self.validator.validate(rule_data)
        assert not result.has_errors()

    def test_nested_stateful_nodes_allowed(self):
        """Nested stateful nodes under sequences/groups should be allowed (only top-level is restricted)."""
        rule_data = {
            "condition_dsl": {
                "type": "sequence",
                "steps": [
                    {
                        "type": "group",
                        "op": "AND",
                        "children": [
                            {"type": "condition", "field": "a", "op": "==", "value": 1},
                        ],
                    },
                    {
                        "type": "group",
                        "op": "OR",
                        "children": [
                            {"type": "condition", "field": "b", "op": "==", "value": 2},
                        ],
                    },
                ],
            }
        }
        result = self.validator.validate(rule_data)
        # Should not error due to mixing at top level
        assert not result.has_errors()

    def test_empty_condition_dsl(self):
        """Empty condition_dsl should be valid (no stateful nodes to validate)."""
        rule_data = {"condition_dsl": {}}
        result = self.validator.validate(rule_data)
        assert not result.has_errors()

    def test_simple_condition_valid(self):
        """Simple non-stateful condition should be valid."""
        rule_data = {
            "condition_dsl": {
                "type": "condition",
                "field": "age",
                "op": ">",
                "value": 18,
            }
        }
        result = self.validator.validate(rule_data)
        assert not result.has_errors()

    def test_group_with_simple_conditions(self):
        """Group with simple conditions should be valid."""
        rule_data = {
            "condition_dsl": {
                "type": "group",
                "op": "AND",
                "children": [
                    {"type": "condition", "field": "age", "op": ">", "value": 18},
                    {
                        "type": "condition",
                        "field": "status",
                        "op": "==",
                        "value": "active",
                    },
                ],
            }
        }
        result = self.validator.validate(rule_data)
        assert not result.has_errors()

    def test_multiple_top_level_sequences_error(self):
        """Multiple sequence children at top level should error (mutual exclusivity)."""
        rule_data = {
            "condition_dsl": {
                "type": "group",
                "op": "AND",
                "children": [
                    {
                        "type": "sequence",
                        "steps": [
                            {"type": "condition", "field": "a", "op": "==", "value": 1},
                            {"type": "condition", "field": "b", "op": "==", "value": 2},
                        ],
                    },
                    {
                        "type": "sequence",
                        "steps": [
                            {"type": "condition", "field": "c", "op": "==", "value": 3},
                            {"type": "condition", "field": "d", "op": "==", "value": 4},
                        ],
                    },
                ],
            }
        }
        result = self.validator.validate(rule_data)
        # Multiple sequences are OK (they're the same family)
        assert not result.has_errors()
