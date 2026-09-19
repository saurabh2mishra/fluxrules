"""Tests for the FluxRules exception hierarchy."""

from __future__ import annotations

import pytest

from fluxrules.domain.errors import FluxRulesError
from fluxrules.exceptions import (
    ActionExecutionError,
    ConfigurationError,
    DSLParseError,
    EngineError,
    FluxRulesException,
    RepositoryError,
    RuleEvaluationError,
    RuleValidationError,
)


class TestExceptionHierarchy:
    """Verify inheritance and attribute storage for custom exceptions."""

    def test_base_inherits_from_fluxrules_error(self) -> None:
        """FluxRulesException should be a subclass of FluxRulesError."""
        assert issubclass(FluxRulesException, FluxRulesError)

    @pytest.mark.parametrize(
        "exc_cls",
        [
            RuleValidationError,
            RuleEvaluationError,
            DSLParseError,
            RepositoryError,
            ConfigurationError,
            EngineError,
            ActionExecutionError,
        ],
    )
    def test_all_exceptions_inherit_from_base(self, exc_cls: type) -> None:
        """Every typed exception is a FluxRulesException."""
        assert issubclass(exc_cls, FluxRulesException)

    def test_rule_validation_error_attributes(self) -> None:
        """RuleValidationError stores rule_id and field."""
        exc = RuleValidationError("bad rule", rule_id="r1", field="priority")
        assert exc.rule_id == "r1"
        assert exc.field == "priority"
        assert "bad rule" in str(exc)

    def test_rule_evaluation_error_attributes(self) -> None:
        """RuleEvaluationError stores rule_id."""
        exc = RuleEvaluationError("eval fail", rule_id="r2")
        assert exc.rule_id == "r2"

    def test_dsl_parse_error_attributes(self) -> None:
        """DSLParseError stores rule_id and detail."""
        exc = DSLParseError("parse fail", rule_id="r3", detail="missing op")
        assert exc.rule_id == "r3"
        assert exc.detail == "missing op"

    def test_engine_error_attributes(self) -> None:
        """EngineError stores engine_type."""
        exc = EngineError("init fail", engine_type="PHREAK")
        assert exc.engine_type == "PHREAK"

    def test_action_execution_error_attributes(self) -> None:
        """ActionExecutionError stores action_name."""
        exc = ActionExecutionError("action fail", action_name="send_alert")
        assert exc.action_name == "send_alert"

    def test_exception_codes_are_set(self) -> None:
        """Each exception class exposes a stable code attribute."""
        assert RuleValidationError.code == "RULE_VALIDATION_ERROR"
        assert EngineError.code == "ENGINE_ERROR"
        assert RepositoryError.code == "REPOSITORY_ERROR"

    def test_catch_exception_via_base(self) -> None:
        """Catching FluxRulesError should also catch typed exceptions."""
        with pytest.raises(FluxRulesError):
            raise RuleValidationError("test")
