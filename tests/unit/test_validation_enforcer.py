"""Unit tests for validation enforcer."""

import pytest

from fluxrules.services.validation_enforcer import ValidationEnforcer
from fluxrules.services.validation_gateway import ValidationException
from fluxrules.services.validators import ValidationResult


class TestValidationEnforcer:
    """Tests for ValidationEnforcer."""

    def test_enforce_skip_mode(self):
        """Test that skip mode bypasses enforcement."""
        result = ValidationResult()
        result.add_error("error1", "Test error")

        # Should not raise in skip mode
        ValidationEnforcer.enforce(result, mode="skip")

    def test_enforce_strict_mode_with_errors(self):
        """Test that strict mode raises on errors."""
        result = ValidationResult()
        result.add_error("error1", "Test error")

        with pytest.raises(ValidationException):
            ValidationEnforcer.enforce(result, mode="strict")

    def test_enforce_strict_mode_no_errors(self):
        """Test that strict mode passes with no errors."""
        result = ValidationResult()
        result.add_warning("warning1", "Test warning")

        # Should not raise
        ValidationEnforcer.enforce(result, mode="strict")

    def test_enforce_warning_mode(self):
        """Test that warning mode logs but doesn't raise."""
        result = ValidationResult()
        result.add_error("error1", "Test error")
        result.add_warning("warning1", "Test warning")

        # Should not raise in warning mode
        ValidationEnforcer.enforce(result, mode="warning")

    def test_get_decision_with_errors_strict(self):
        """Test decision with errors in strict mode."""
        result = ValidationResult()
        result.add_error("error1", "Test error")

        decision = ValidationEnforcer.get_decision(result, mode="strict")

        assert decision["should_proceed"] is False
        assert decision["errors"] == 1

    def test_get_decision_no_errors_strict(self):
        """Test decision with no errors in strict mode."""
        result = ValidationResult()

        decision = ValidationEnforcer.get_decision(result, mode="strict")

        assert decision["should_proceed"] is True
        assert decision["errors"] == 0

    def test_get_decision_with_warnings(self):
        """Test decision with warnings."""
        result = ValidationResult()
        result.add_warning("warning1", "Test warning")

        decision = ValidationEnforcer.get_decision(result, mode="strict")

        assert decision["should_proceed"] is True
        assert decision["warnings"] == 1

    def test_get_report_summary_no_issues(self):
        """Test summary with no issues."""
        result = ValidationResult()

        summary = ValidationEnforcer.get_report_summary(result, rule_name="Test Rule")

        assert "✅" in summary
        assert "No issues" in summary

    def test_get_report_summary_with_errors(self):
        """Test summary with errors."""
        result = ValidationResult()
        result.add_error("error1", "Test error 1")
        result.add_error("error2", "Test error 2")

        summary = ValidationEnforcer.get_report_summary(result, rule_name="Test Rule")

        assert "❌" in summary
        assert "2 error" in summary

    def test_get_report_summary_with_warnings(self):
        """Test summary with warnings."""
        result = ValidationResult()
        result.add_warning("warning1", "Test warning")

        summary = ValidationEnforcer.get_report_summary(result, rule_name="Test Rule")

        assert "⚠️" in summary
        assert "1 warning" in summary

    def test_get_report_summary_mixed_issues(self):
        """Test summary with both errors and warnings."""
        result = ValidationResult()
        result.add_error("error1", "Test error")
        result.add_warning("warning1", "Test warning")

        summary = ValidationEnforcer.get_report_summary(result, rule_name="Test Rule")

        assert "❌" in summary
        assert "⚠️" in summary
        assert "1 error" in summary
        assert "1 warning" in summary

    def test_enforce_with_rule_name(self):
        """Test enforcement with rule name in logging."""
        result = ValidationResult()
        result.add_warning("warning1", "Test warning")

        # Should not raise
        ValidationEnforcer.enforce(result, mode="warning", rule_name="My Rule")

    def test_get_report_summary_truncates_long_lists(self):
        """Test that summary truncates long error lists."""
        result = ValidationResult()
        for i in range(5):
            result.add_error(f"error{i}", f"Error {i}")

        summary = ValidationEnforcer.get_report_summary(result)

        assert "5 error" in summary
        assert "and 2 more" in summary  # Should show truncation

    def test_decision_warning_mode_with_errors(self):
        """Test decision in warning mode with errors."""
        result = ValidationResult()
        result.add_error("error1", "Test error")

        decision = ValidationEnforcer.get_decision(result, mode="warning")

        assert decision["should_proceed"] is True
        assert decision["mode"] == "warning"
