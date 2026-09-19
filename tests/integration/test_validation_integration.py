"""Integration tests for unified validation system."""

import json
from unittest.mock import Mock

import pytest
from sqlalchemy.orm import Session

from fluxrules.services.validation_gateway import ValidationException, ValidationGateway
from fluxrules.services.validators import ValidationResult


class TestValidationIntegration:
    """Integration tests for the unified validation system."""

    @pytest.fixture
    def db(self) -> Session:
        """Create a mock database session."""
        return Mock(spec=Session)

    @pytest.fixture
    def gateway(self, db: Session) -> ValidationGateway:
        """Create a ValidationGateway."""
        return ValidationGateway(db)

    def test_valid_rule_passes_all_validators(self, gateway: ValidationGateway):
        """Test that a fully valid rule passes all validators."""
        rule_data = {
            "name": "Valid Rule",
            "description": "A valid rule for testing",
            "group": "test_group",
            "priority": 10,
            "enabled": True,
            "condition_dsl": {
                "type": "AND",
                "children": [
                    {"type": "condition", "field": "age", "op": ">=", "value": 18},
                    {
                        "type": "OR",
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
                                "value": "pending",
                            },
                        ],
                    },
                ],
            },
            "action": "approve_user",
        }

        result = gateway.validate(rule_data, mode="warning")

        assert isinstance(result, ValidationResult)
        assert not result.has_errors()

    def test_invalid_rule_fails_strict_mode(self, gateway: ValidationGateway):
        """Test that invalid rule fails in strict mode."""
        rule_data = {
            # Missing required fields
            "group": "test_group",
        }

        with pytest.raises(ValidationException) as exc_info:
            gateway.validate(rule_data, mode="strict")

        assert "validation failed" in str(exc_info.value).lower()
        assert exc_info.value.validation_result.has_errors()

    def test_invalid_rule_passes_warning_mode(self, gateway: ValidationGateway):
        """Test that invalid rule passes in warning mode."""
        rule_data = {
            # Missing required fields
            "group": "test_group",
        }

        result = gateway.validate(rule_data, mode="warning")

        assert isinstance(result, ValidationResult)
        # Should have errors but not raise

    def test_complex_nested_condition_validation(self, gateway: ValidationGateway):
        """Test validation of complex nested conditions."""
        rule_data = {
            "name": "Complex Rule",
            "condition_dsl": {
                "type": "AND",
                "children": [
                    {
                        "type": "OR",
                        "children": [
                            {
                                "type": "AND",
                                "children": [
                                    {
                                        "type": "condition",
                                        "field": "field1",
                                        "op": "==",
                                        "value": "value1",
                                    },
                                    {
                                        "type": "condition",
                                        "field": "field2",
                                        "op": "!=",
                                        "value": "value2",
                                    },
                                ],
                            },
                            {
                                "type": "condition",
                                "field": "field3",
                                "op": "in",
                                "value": [1, 2, 3],
                            },
                        ],
                    },
                ],
            },
            "action": "process",
        }

        result = gateway.validate(rule_data, mode="warning")

        assert not result.has_errors()

    def test_normalize_pydantic_model_with_json_dsl(self, gateway: ValidationGateway):
        """Test normalizing Pydantic model with JSON-encoded condition_dsl."""
        mock_model = Mock()
        condition_json = json.dumps({"type": "condition", "field": "age", "op": ">=", "value": 18})
        mock_model.model_dump.return_value = {
            "name": "Test Rule",
            "condition_dsl": condition_json,
            "action": "approve",
            "group": "test",
        }

        rule_dict = gateway._normalize_rule_data(mock_model)

        assert isinstance(rule_dict["condition_dsl"], dict)
        assert rule_dict["condition_dsl"]["type"] == "condition"

    def test_validate_and_log_integration(self, gateway: ValidationGateway):
        """Test validate_and_log convenience method."""
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

        rule_dict, result = gateway.validate_and_log(rule_data, user_id=123, mode="warning")

        assert isinstance(rule_dict, dict)
        assert isinstance(result, ValidationResult)
        assert rule_dict["name"] == "Test Rule"

    def test_multiple_validation_issues_aggregated(self, gateway: ValidationGateway):
        """Test that multiple validation issues are aggregated."""
        rule_data = {
            # Missing name and action
            "condition_dsl": {"type": "invalid"},  # Invalid condition
        }

        result = gateway.validate(rule_data, mode="warning")

        errors = result.get_errors()
        assert len(errors) > 0  # Should have multiple errors
        # Errors should come from different validators

    def test_validation_result_serialization(self, gateway: ValidationGateway):
        """Test that validation results can be serialized."""
        rule_data = {
            "name": "Test",
            # Missing required fields
        }

        result = gateway.validate(rule_data, mode="warning")

        # Should be able to serialize to dict
        result_dict = result.to_dict()
        assert isinstance(result_dict, dict)
        assert "issues" in result_dict
        assert "has_errors" in result_dict
        assert "error_count" in result_dict

    def test_validator_info_retrieval(self, gateway: ValidationGateway):
        """Test getting information about configured validators."""
        info = gateway.get_validator_info()

        assert "validators" in info
        assert "count" in info
        assert info["count"] == 7  # 7 validators (including StatefulDSLValidator)
        assert len(info["validators"]) == 7
        # Check for expected validators
        validator_names = info["validators"]
        assert "StructuralValidator" in validator_names
        assert "DuplicateValidator" in validator_names
        assert "PriorityValidator" in validator_names
        assert "BRMSValidator" in validator_names
        assert "ActionValidator" in validator_names
        assert "ReferentialValidator" in validator_names

    def test_empty_rule_data(self, gateway: ValidationGateway):
        """Test handling of empty rule data."""
        result = gateway.validate({}, mode="warning")

        assert result.has_errors()
        errors = result.get_errors()
        # Should have errors for missing required fields
        assert any("name" in e.message for e in errors)

    def test_rule_with_metadata(self, gateway: ValidationGateway):
        """Test validating rule with metadata."""
        rule_data = {
            "name": "Rule with Metadata",
            "condition_dsl": {
                "type": "condition",
                "field": "age",
                "op": ">=",
                "value": 18,
            },
            "action": "approve",
            "rule_metadata": {
                "department": "HR",
                "owner": "john.doe",
                "tags": ["approval", "automation"],
            },
        }

        result = gateway.validate(rule_data, mode="warning")

        assert not result.has_errors()

    def test_disabled_rule_validation(self, gateway: ValidationGateway):
        """Test validating disabled rules."""
        rule_data = {
            "name": "Disabled Rule",
            "enabled": False,
            "condition_dsl": {
                "type": "condition",
                "field": "age",
                "op": ">=",
                "value": 18,
            },
            "action": "process",
        }

        result = gateway.validate(rule_data, mode="warning")

        # Should pass even though disabled
        assert not result.has_errors()
