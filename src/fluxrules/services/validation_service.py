from __future__ import annotations

from fluxrules.domain.models import Ruleset
from fluxrules.domain.predicates import OPERATORS
from fluxrules.ports.validation import ValidationIssue, ValidationSeverity, Validator


class BuiltinRulesetValidator(Validator):
    """Default built-in validator for basic ruleset structural checks."""

    def validate(self, ruleset: Ruleset) -> list[ValidationIssue]:
        issues: list[ValidationIssue] = []
        if not ruleset.rules:
            issues.append(
                ValidationIssue(
                    message="Ruleset is empty",
                    severity=ValidationSeverity.ERROR,
                    validator=self.name,
                )
            )

        ids = [rule.id for rule in ruleset.rules]
        if len(ids) != len(set(ids)):
            issues.append(
                ValidationIssue(
                    message="Ruleset has duplicate rule ids",
                    severity=ValidationSeverity.ERROR,
                    validator=self.name,
                )
            )

        for rule in ruleset.rules:
            if not rule.conditions:
                # Distinguish two very different situations that both surface
                # as an empty flat view: a rule that genuinely carries no
                # logic (a defect), and one whose ``condition_dsl`` is present
                # but not expressible as a flat conjunction (fine - the
                # DSL-based engines evaluate it correctly).
                dsl = getattr(rule, "condition_dsl", None)
                if dsl:
                    issues.append(
                        ValidationIssue(
                            message=(
                                f"Rule '{rule.id}' has a condition_dsl that cannot be "
                                "represented as a flat condition list; evaluate it with "
                                "PhreakEngine rather than the reference "
                                "evaluator"
                            ),
                            severity=ValidationSeverity.INFO,
                            rule_id=rule.id,
                            validator=self.name,
                        )
                    )
                else:
                    issues.append(
                        ValidationIssue(
                            message=f"Rule '{rule.id}' has no conditions",
                            severity=ValidationSeverity.WARNING,
                            rule_id=rule.id,
                            validator=self.name,
                        )
                    )
            for condition in rule.conditions:
                if condition.operator not in OPERATORS:
                    issues.append(
                        ValidationIssue(
                            message=f"Rule '{rule.id}' uses unsupported operator '{condition.operator}'",
                            severity=ValidationSeverity.ERROR,
                            rule_id=rule.id,
                            validator=self.name,
                        )
                    )

        return issues


class ValidationService:
    """Composable validation service with plugin support.

    Supports registering custom validators alongside built-in ones.
    """

    def __init__(self, validators: list[Validator] | None = None):
        self._validators: list[Validator] = validators or [BuiltinRulesetValidator()]

    def register_validator(self, validator: Validator) -> None:
        """Register a custom validator plugin."""
        self._validators.append(validator)

    def unregister_validator(self, validator_type: type) -> None:
        """Remove all validators of a given type."""
        self._validators = [v for v in self._validators if not isinstance(v, validator_type)]

    @property
    def validators(self) -> list[Validator]:
        """List of registered validators."""
        return list(self._validators)

    def validate_ruleset(self, ruleset: Ruleset) -> list[str]:
        """Validate a ruleset and return human-readable issue strings.

        Returns a list of issue message strings.
        """
        issues: list[str] = []
        for validator in self._validators:
            for issue in validator.validate(ruleset):
                issues.append(issue.message)
        return issues

    def validate_ruleset_detailed(self, ruleset: Ruleset) -> list[ValidationIssue]:
        """Validate a ruleset and return detailed ValidationIssue objects."""
        issues: list[ValidationIssue] = []
        for validator in self._validators:
            issues.extend(validator.validate(ruleset))
        return issues
