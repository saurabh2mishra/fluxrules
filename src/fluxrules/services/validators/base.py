"""Base validator interface for rule validation.

All validators implement this interface to provide consistent validation behavior
across the FluxRules system.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from dataclasses import field as dataclass_field
from enum import Enum
from typing import Any


class SeverityLevel(Enum):
    """Severity levels for validation issues."""

    ERROR = "error"  # Blocks rule creation
    WARNING = "warning"  # Logs but allows creation
    INFO = "info"  # Informational only


@dataclass
class ValidationIssue:
    """A single validation issue."""

    type: str
    message: str
    severity: SeverityLevel
    field: str | None = None
    rule_id: int | None = None
    details: dict[str, Any] = dataclass_field(default_factory=dict)

    def __str__(self) -> str:
        """String representation."""
        prefix = f"[{self.severity.value.upper()}]"
        field_str = f" ({self.field})" if self.field else ""
        return f"{prefix} {self.type}{field_str}: {self.message}"


@dataclass
class ValidationResult:
    """Result of validation by a single validator."""

    issues: list[ValidationIssue] = dataclass_field(default_factory=list)

    def add_issue(
        self,
        issue_type: str,
        message: str,
        severity: SeverityLevel,
        field: str | None = None,
        rule_id: int | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        """Add a validation issue."""
        issue = ValidationIssue(
            type=issue_type,
            message=message,
            severity=severity,
            field=field,
            rule_id=rule_id,
            details=details or {},
        )
        self.issues.append(issue)

    def add_error(
        self,
        issue_type: str,
        message: str,
        field: str | None = None,
        rule_id: int | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        """Add error-level issue."""
        self.add_issue(issue_type, message, SeverityLevel.ERROR, field, rule_id, details)

    def add_warning(
        self,
        issue_type: str,
        message: str,
        field: str | None = None,
        rule_id: int | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        """Add warning-level issue."""
        self.add_issue(issue_type, message, SeverityLevel.WARNING, field, rule_id, details)

    def add_info(
        self,
        issue_type: str,
        message: str,
        field: str | None = None,
        rule_id: int | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        """Add info-level issue."""
        self.add_issue(issue_type, message, SeverityLevel.INFO, field, rule_id, details)

    def has_errors(self) -> bool:
        """Check if there are any errors."""
        return any(issue.severity == SeverityLevel.ERROR for issue in self.issues)

    def has_warnings(self) -> bool:
        """Check if there are any warnings."""
        return any(issue.severity == SeverityLevel.WARNING for issue in self.issues)

    def get_errors(self) -> list[ValidationIssue]:
        """Get all errors."""
        return [issue for issue in self.issues if issue.severity == SeverityLevel.ERROR]

    def get_warnings(self) -> list[ValidationIssue]:
        """Get all warnings."""
        return [issue for issue in self.issues if issue.severity == SeverityLevel.WARNING]

    def merge(self, other: ValidationResult) -> None:
        """Merge another result into this one."""
        self.issues.extend(other.issues)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "issues": [
                {
                    "type": issue.type,
                    "message": issue.message,
                    "severity": issue.severity.value,
                    "field": issue.field,
                    "rule_id": issue.rule_id,
                    "details": issue.details,
                }
                for issue in self.issues
            ],
            "has_errors": self.has_errors(),
            "has_warnings": self.has_warnings(),
            "error_count": len(self.get_errors()),
            "warning_count": len(self.get_warnings()),
        }

    def __str__(self) -> str:
        """String representation."""
        if not self.issues:
            return "✅ No validation issues"

        lines = [f"📋 Validation Report ({len(self.issues)} issues):"]
        for issue in self.issues:
            lines.append(f"  {issue}")
        return "\n".join(lines)


class Validator(ABC):
    """Base class for all validators.

    Subclasses implement specific validation logic for different aspects
    of rule validation.
    """

    @abstractmethod
    def validate(self, rule_data: dict[str, Any]) -> ValidationResult:
        """Validate rule data and return result.

        Args:
            rule_data: Rule data to validate (dict format)

        Returns:
            ValidationResult with any issues found
        """

    @property
    @abstractmethod
    def validator_name(self) -> str:
        """Name of this validator."""


class CompositeValidator(Validator):
    """Composes multiple validators into a single validation pass."""

    def __init__(self, validators: list[Validator], name: str = "CompositeValidator"):
        """Initialize with list of validators.

        Args:
            validators: List of validators to compose
            name: Name of this composite validator
        """
        self.validators = validators
        self._name = name

    def validate(self, rule_data: dict[str, Any]) -> ValidationResult:
        """Run all validators and merge results.

        Args:
            rule_data: Rule data to validate

        Returns:
            ValidationResult with merged issues from all validators
        """
        result = ValidationResult()
        for validator in self.validators:
            sub_result = validator.validate(rule_data)
            result.merge(sub_result)
        return result

    @property
    def validator_name(self) -> str:
        """Return name."""
        return self._name
