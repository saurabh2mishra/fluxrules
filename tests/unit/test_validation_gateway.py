"""Unit tests for validation gateway."""

from unittest.mock import Mock

import pytest
from sqlalchemy.orm import Session

from fluxrules.services.validation_gateway import ValidationException, ValidationGateway
from fluxrules.services.validators import ValidationResult


class TestValidationGateway:
    """Tests for ValidationGateway."""

    @pytest.fixture
    def mock_db(self) -> Session:
        """Create a mock database session."""
        return Mock(spec=Session)

    @pytest.fixture
    def gateway(self, mock_db: Session) -> ValidationGateway:
        """Create a ValidationGateway instance."""
        return ValidationGateway(mock_db)

    def test_initialization(self, gateway: ValidationGateway):
        """Test gateway initialization."""
        assert gateway.db is not None
        assert (
            gateway.get_validator_info()["count"] == 7
        )  # 7 validators (including StatefulDSLValidator)

    def test_validate_valid_rule(self, gateway: ValidationGateway):
        """Test validating a valid rule."""
        rule_data = {
            "name": "Test Rule",
            "condition_dsl": {
                "type": "condition",
                "field": "age",
                "op": "==",
                "value": 25,
            },
            "action": "log_action",
            "group": "default",
        }

        result = gateway.validate(rule_data, mode="warning")

        assert isinstance(result, ValidationResult)

    def test_validate_missing_required_field(self, gateway: ValidationGateway):
        """Test validation fails with missing required field."""
        rule_data = {
            "condition_dsl": {
                "type": "condition",
                "field": "age",
                "op": "==",
                "value": 25,
            },
            "action": "log_action",
        }

        with pytest.raises(ValidationException) as exc_info:
            gateway.validate(rule_data, mode="strict")

        assert "validation failed" in str(exc_info.value).lower()

    def test_validate_skip_mode(self, gateway: ValidationGateway):
        """Test that skip mode bypasses validation."""
        rule_data = {}  # Invalid, but should pass in skip mode

        result = gateway.validate(rule_data, mode="skip")

        assert len(result.issues) == 0

    def test_validate_warning_mode_allows_errors(self, gateway: ValidationGateway):
        """Test that warning mode allows errors but logs them."""
        rule_data = {
            # Missing required fields
            "action": "log_action",
        }

        # Should not raise in warning mode
        result = gateway.validate(rule_data, mode="warning")

        assert isinstance(result, ValidationResult)

    def test_normalize_dict_input(self, gateway: ValidationGateway):
        """Test normalizing dict input."""
        rule_dict = {"name": "Test", "action": "log"}

        normalized = gateway._normalize_rule_data(rule_dict)

        assert normalized == rule_dict
        assert isinstance(normalized, dict)

    def test_normalize_pydantic_model(self, gateway: ValidationGateway):
        """Test normalizing Pydantic model input."""
        mock_model = Mock()
        mock_model.model_dump.return_value = {
            "name": "Test",
            "action": "log",
            "condition_dsl": '{"type": "condition"}',
        }

        normalized = gateway._normalize_rule_data(mock_model)

        assert isinstance(normalized, dict)
        assert normalized["name"] == "Test"

    def test_normalize_sqlalchemy_model(self, gateway: ValidationGateway):
        """Test normalizing SQLAlchemy model input."""
        # Test with a simple object that has __table__ attribute
        mock_model = Mock()
        mock_model.__dict__ = {"name": "Test", "action": "log"}
        # hasattr will return True for __table__ but we won't use it
        # Instead test the fallback __dict__ path

        normalized = gateway._normalize_rule_data(mock_model)

        assert isinstance(normalized, dict)

    def test_validate_and_log(self, gateway: ValidationGateway):
        """Test validate_and_log method."""
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

    def test_json_parsing_in_normalization(self, gateway: ValidationGateway):
        """Test that JSON strings are parsed in normalization."""
        mock_model = Mock()
        mock_model.model_dump.return_value = {
            "name": "Test",
            "action": "log",
            "condition_dsl": '{"type": "condition", "field": "age", "op": "==", "value": 25}',
        }

        normalized = gateway._normalize_rule_data(mock_model)

        assert isinstance(normalized["condition_dsl"], dict)
        assert normalized["condition_dsl"]["type"] == "condition"


class TestValidationException:
    """Tests for ValidationException."""

    def test_exception_creation(self):
        """Test creating ValidationException."""
        result = ValidationResult()
        result.add_error("test_error", "Test error message")

        exc = ValidationException("Test message", result)

        assert exc.message == "Test message"
        assert exc.validation_result is result

    def test_exception_string(self):
        """Test exception string representation."""
        result = ValidationResult()
        result.add_error("test_error", "Test error message")

        exc = ValidationException("Test message", result)

        assert "Test message" in str(exc)
