"""Unit tests for unified validation system."""

from unittest.mock import Mock

import pytest
from sqlalchemy.orm import Session

from fluxrules.services.validators import (
    ActionValidator,
    BRMSValidator,
    CompositeValidator,
    DuplicateValidator,
    PriorityValidator,
    ReferentialValidator,
    StructuralValidator,
    ValidationResult,
)


class TestValidationResult:
    """Tests for ValidationResult class."""

    def test_add_error(self):
        """Test adding error to result."""
        result = ValidationResult()
        result.add_error("test_error", "Test error message", field="test_field")

        assert result.has_errors()
        assert not result.has_warnings()
        assert len(result.get_errors()) == 1
        assert result.get_errors()[0].type == "test_error"

    def test_add_warning(self):
        """Test adding warning to result."""
        result = ValidationResult()
        result.add_warning("test_warning", "Test warning message", field="test_field")

        assert not result.has_errors()
        assert result.has_warnings()
        assert len(result.get_warnings()) == 1

    def test_merge_results(self):
        """Test merging validation results."""
        result1 = ValidationResult()
        result1.add_error("error1", "Error 1")

        result2 = ValidationResult()
        result2.add_warning("warning1", "Warning 1")

        result1.merge(result2)

        assert result1.has_errors()
        assert result1.has_warnings()
        assert len(result1.get_errors()) == 1
        assert len(result1.get_warnings()) == 1

    def test_to_dict(self):
        """Test converting result to dict."""
        result = ValidationResult()
        result.add_error("error1", "Error 1")
        result.add_warning("warning1", "Warning 1")

        result_dict = result.to_dict()

        assert result_dict["error_count"] == 1
        assert result_dict["warning_count"] == 1
        assert result_dict["has_errors"] is True
        assert result_dict["has_warnings"] is True


class TestStructuralValidator:
    """Tests for StructuralValidator."""

    def test_required_fields_missing(self):
        """Test that missing required fields are detected."""
        validator = StructuralValidator()

        result = validator.validate({})

        assert result.has_errors()
        errors = result.get_errors()
        assert any("name" in e.message for e in errors)
        assert any("condition_dsl" in e.message for e in errors)
        assert any("action" in e.message for e in errors)

    def test_valid_rule(self):
        """Test that valid rule passes validation."""
        validator = StructuralValidator()

        rule_data = {
            "name": "Test Rule",
            "condition_dsl": {
                "type": "condition",
                "field": "age",
                "op": "==",
                "value": 25,
            },
            "action": "log_action",
        }

        result = validator.validate(rule_data)

        assert not result.has_errors()

    def test_invalid_dsl_structure(self):
        """Test that invalid DSL structure is detected."""
        validator = StructuralValidator()

        rule_data = {
            "name": "Test Rule",
            "condition_dsl": "not a dict",
            "action": "log_action",
        }

        result = validator.validate(rule_data)

        assert result.has_errors()

    def test_dsl_missing_type(self):
        """Test that DSL missing type field is detected."""
        validator = StructuralValidator()

        rule_data = {
            "name": "Test Rule",
            "condition_dsl": {"field": "age", "op": "==", "value": 25},
            "action": "log_action",
        }

        result = validator.validate(rule_data)

        assert result.has_errors()
        assert any("type" in e.message for e in result.get_errors())

    def test_invalid_operator(self):
        """Test that invalid operator is detected."""
        validator = StructuralValidator()

        rule_data = {
            "name": "Test Rule",
            "condition_dsl": {
                "type": "condition",
                "field": "age",
                "op": "invalid_op",
                "value": 25,
            },
            "action": "log_action",
        }

        result = validator.validate(rule_data)

        assert result.has_errors()
        assert any("operator" in e.message for e in result.get_errors())

    def test_group_dsl(self):
        """Test validation of group DSL."""
        validator = StructuralValidator()

        rule_data = {
            "name": "Test Rule",
            "condition_dsl": {
                "type": "AND",
                "children": [
                    {"type": "condition", "field": "age", "op": ">=", "value": 18},
                    {
                        "type": "condition",
                        "field": "status",
                        "op": "==",
                        "value": "active",
                    },
                ],
            },
            "action": "approve",
        }

        result = validator.validate(rule_data)

        assert not result.has_errors()

    def test_name_too_long(self):
        """Test that overly long name is detected."""
        validator = StructuralValidator()

        rule_data = {
            "name": "a" * 256,
            "condition_dsl": {
                "type": "condition",
                "field": "age",
                "op": "==",
                "value": 25,
            },
            "action": "log_action",
        }

        result = validator.validate(rule_data)

        assert result.has_errors()
        assert any("name_too_long" in e.type for e in result.get_errors())


class TestDuplicateValidator:
    """Tests for DuplicateValidator."""

    def test_duplicate_name_warning(self, mock_db: Session):
        """Test that duplicate name generates warning."""
        # Create mock rule in database
        mock_rule = Mock()
        mock_rule.id = 1
        mock_rule.name = "Test Rule"

        # Mock the query chain
        filter_mock = Mock()
        filter_mock.filter.return_value.first.return_value = mock_rule
        mock_db.query.return_value = filter_mock

        validator = DuplicateValidator(mock_db)
        rule_data = {
            "name": "Test Rule",
            "group": "default",
            "condition_dsl": {
                "type": "condition",
                "field": "age",
                "op": "==",
                "value": 25,
            },
            "action": "log_action",
        }

        result = validator.validate(rule_data)

        assert result.has_warnings()
        assert any("duplicate" in w.type for w in result.get_warnings())

    def test_no_duplicate(self, mock_db: Session):
        """Test that non-duplicate rule passes."""
        # Mock the query chain to return no existing rules
        filter_mock = Mock()
        filter_mock.filter.return_value.first.return_value = None
        mock_db.query.return_value = filter_mock

        validator = DuplicateValidator(mock_db)
        rule_data = {
            "name": "Unique Rule",
            "group": "default",
            "condition_dsl": {
                "type": "condition",
                "field": "age",
                "op": "==",
                "value": 25,
            },
            "action": "log_action",
        }

        result = validator.validate(rule_data)

        assert not result.has_errors()
        assert not result.has_warnings()


class TestPriorityValidator:
    """Tests for PriorityValidator."""

    def test_priority_conflict_warning(self, mock_db: Session):
        """Test that priority conflict generates warning."""
        mock_rule1 = Mock()
        mock_rule1.id = 1
        mock_rule1.name = "Rule 1"
        mock_rule2 = Mock()
        mock_rule2.id = 2
        mock_rule2.name = "Rule 2"

        # Mock the query chain
        filter_mock = Mock()
        filter_mock.filter.return_value.all.return_value = [mock_rule1, mock_rule2]
        mock_db.query.return_value = filter_mock

        validator = PriorityValidator(mock_db)
        rule_data = {
            "name": "Test Rule",
            "priority": 10,
            "group": "default",
            "condition_dsl": {
                "type": "condition",
                "field": "age",
                "op": "==",
                "value": 25,
            },
            "action": "log_action",
        }

        result = validator.validate(rule_data)

        assert result.has_warnings()
        assert any("priority" in w.message.lower() for w in result.get_warnings())

    def test_no_priority_conflict(self, mock_db: Session):
        """Test that unique priority passes."""
        # Mock the query chain to return no conflicts
        filter_mock = Mock()
        filter_mock.filter.return_value.all.return_value = []
        mock_db.query.return_value = filter_mock

        validator = PriorityValidator(mock_db)
        rule_data = {
            "name": "Test Rule",
            "priority": 10,
            "group": "default",
            "condition_dsl": {
                "type": "condition",
                "field": "age",
                "op": "==",
                "value": 25,
            },
            "action": "log_action",
        }

        result = validator.validate(rule_data)

        assert not result.has_warnings()


class TestBRMSValidator:
    """Tests for BRMSValidator."""

    def test_contradictory_and_condition(self):
        """Test that contradictory AND conditions are detected."""
        validator = BRMSValidator()

        rule_data = {
            "name": "Bad Rule",
            "condition_dsl": {
                "type": "AND",
                "children": [
                    {
                        "type": "condition",
                        "field": "status",
                        "op": "==",
                        "value": "active",
                    },
                    {
                        "type": "condition",
                        "field": "status",
                        "op": "==",
                        "value": "inactive",
                    },
                ],
            },
            "action": "log_action",
        }

        result = validator.validate(rule_data)

        assert result.has_warnings()
        assert any("contradictory" in w.message.lower() for w in result.get_warnings())

    def test_valid_and_condition(self):
        """Test that valid AND conditions pass."""
        validator = BRMSValidator()

        rule_data = {
            "name": "Good Rule",
            "condition_dsl": {
                "type": "AND",
                "children": [
                    {"type": "condition", "field": "age", "op": ">=", "value": 18},
                    {
                        "type": "condition",
                        "field": "status",
                        "op": "==",
                        "value": "active",
                    },
                ],
            },
            "action": "approve",
        }

        result = validator.validate(rule_data)

        assert not result.has_errors()
        assert not result.has_warnings()


class TestActionValidator:
    """Tests for ActionValidator."""

    def test_missing_action(self):
        """Test that missing action is detected."""
        validator = ActionValidator()

        rule_data = {
            "name": "Test Rule",
            "condition_dsl": {
                "type": "condition",
                "field": "age",
                "op": "==",
                "value": 25,
            },
        }

        result = validator.validate(rule_data)

        assert result.has_errors()
        assert any("action" in e.message.lower() for e in result.get_errors())

    def test_unknown_action_with_registry(self):
        """Test that unknown action is warned when registry available."""
        registry = {"log_action": Mock(), "send_email": Mock()}
        validator = ActionValidator(registry)

        rule_data = {
            "name": "Test Rule",
            "condition_dsl": {
                "type": "condition",
                "field": "age",
                "op": "==",
                "value": 25,
            },
            "action": "unknown_action",
        }

        result = validator.validate(rule_data)

        assert result.has_warnings()
        assert any("unknown" in w.message.lower() for w in result.get_warnings())

    def test_known_action(self):
        """Test that known action passes."""
        registry = {"log_action": Mock()}
        validator = ActionValidator(registry)

        rule_data = {
            "name": "Test Rule",
            "condition_dsl": {
                "type": "condition",
                "field": "age",
                "op": "==",
                "value": 25,
            },
            "action": "log_action",
        }

        result = validator.validate(rule_data)

        assert not result.has_errors()
        assert not result.has_warnings()


class TestReferentialValidator:
    """Tests for ReferentialValidator."""

    def test_field_not_in_schema(self):
        """Test that field not in schema generates warning."""
        schema = {"name": str, "age": int, "status": str}
        validator = ReferentialValidator(schema=schema)

        rule_data = {
            "name": "Test Rule",
            "condition_dsl": {
                "type": "condition",
                "field": "unknown_field",
                "op": "==",
                "value": 25,
            },
            "action": "log_action",
        }

        result = validator.validate(rule_data)

        assert result.has_warnings()
        assert any("field" in w.message.lower() for w in result.get_warnings())

    def test_field_in_schema(self):
        """Test that field in schema passes."""
        schema = {"name": str, "age": int, "status": str}
        validator = ReferentialValidator(schema=schema)

        rule_data = {
            "name": "Test Rule",
            "condition_dsl": {
                "type": "condition",
                "field": "age",
                "op": "==",
                "value": 25,
            },
            "action": "log_action",
        }

        result = validator.validate(rule_data)

        assert not result.has_warnings()


class TestCompositeValidator:
    """Tests for CompositeValidator."""

    def test_composite_runs_all_validators(self):
        """Test that composite validator runs all sub-validators."""
        validator1 = Mock()
        result1 = ValidationResult()
        result1.add_error("error1", "Error from validator 1")
        validator1.validate.return_value = result1

        validator2 = Mock()
        result2 = ValidationResult()
        result2.add_warning("warning1", "Warning from validator 2")
        validator2.validate.return_value = result2

        composite = CompositeValidator([validator1, validator2])
        result = composite.validate({"name": "test"})

        assert result.has_errors()
        assert result.has_warnings()
        assert len(result.get_errors()) == 1
        assert len(result.get_warnings()) == 1


@pytest.fixture
def mock_db() -> Session:
    """Create a mock database session."""
    return Mock(spec=Session)
