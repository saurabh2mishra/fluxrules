"""Port interface for pluggable validation strategies."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum

from fluxrules.domain.models import Ruleset


class ValidationSeverity(Enum):
    """Severity level for validation issues."""

    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


@dataclass(frozen=True)
class ValidationIssue:
    """A single validation finding."""

    message: str
    severity: ValidationSeverity = ValidationSeverity.WARNING
    rule_id: int | str | None = None
    validator: str = ""


class Validator(ABC):
    """Abstract validator strategy.

    Implement this to create custom validation plugins that can
    be registered with the ValidationService.
    """

    @abstractmethod
    def validate(self, ruleset: Ruleset) -> list[ValidationIssue]:
        """Validate a ruleset and return issues found."""

    @property
    def name(self) -> str:
        """Human-readable name of this validator."""
        return type(self).__name__
