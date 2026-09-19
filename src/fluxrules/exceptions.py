"""Exception hierarchy for FluxRules.

Provides typed exceptions for different failure scenarios,
enabling precise error handling and debugging. All exceptions
inherit from ``FluxRulesException`` which itself extends the
existing ``FluxRulesError`` base so that any catch of the
legacy base still works.
"""

from __future__ import annotations

from fluxrules.domain.errors import FluxRulesError


class FluxRulesException(FluxRulesError):
    """Base exception for all FluxRules typed errors.

    Attributes:
        message: Human-readable error description.
    """

    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(message)


class RuleValidationError(FluxRulesException):
    """Raised when rule validation fails.

    Attributes:
        rule_id: ID of the invalid rule, if available.
        field: Field that failed validation, if available.
    """

    code = "RULE_VALIDATION_ERROR"

    def __init__(
        self,
        message: str,
        rule_id: str | None = None,
        field: str | None = None,
    ) -> None:
        super().__init__(message)
        self.rule_id = rule_id
        self.field = field


class RuleEvaluationError(FluxRulesException):
    """Raised when a runtime error occurs during rule evaluation.

    Attributes:
        rule_id: ID of the rule that failed, if available.
    """

    code = "RULE_EVALUATION_ERROR"

    def __init__(
        self,
        message: str,
        rule_id: str | None = None,
    ) -> None:
        super().__init__(message)
        self.rule_id = rule_id


class DSLParseError(FluxRulesException):
    """Raised when DSL syntax or parsing fails.

    Attributes:
        rule_id: ID of the rule containing the invalid DSL.
        detail: Additional parse-error detail.
    """

    code = "DSL_PARSE_ERROR"

    def __init__(
        self,
        message: str,
        rule_id: str | None = None,
        detail: str | None = None,
    ) -> None:
        super().__init__(message)
        self.rule_id = rule_id
        self.detail = detail


class RepositoryError(FluxRulesException):
    """Raised when a database / repository operation fails."""

    code = "REPOSITORY_ERROR"


class ConfigurationError(FluxRulesException):
    """Raised when an invalid configuration is detected."""

    code = "CONFIGURATION_ERROR"


class EngineError(FluxRulesException):
    """Raised when engine initialisation or operation fails.

    Attributes:
        engine_type: Name of the engine that errored.
    """

    code = "ENGINE_ERROR"

    def __init__(
        self,
        message: str,
        engine_type: str | None = None,
    ) -> None:
        super().__init__(message)
        self.engine_type = engine_type


class ActionExecutionError(FluxRulesException):
    """Raised when a rule action fails to execute.

    Attributes:
        action_name: Name of the action that failed.
    """

    code = "ACTION_EXECUTION_ERROR"

    def __init__(
        self,
        message: str,
        action_name: str | None = None,
    ) -> None:
        super().__init__(message)
        self.action_name = action_name
