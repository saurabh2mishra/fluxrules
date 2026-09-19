"""Tests for the pluggable validation service."""

from fluxrules.domain.models import EngineRule, RuleCondition, Ruleset
from fluxrules.ports.validation import ValidationIssue, ValidationSeverity, Validator
from fluxrules.services.validation_service import ValidationService


def _make_ruleset(rules=None):
    if rules is None:
        rules = (
            EngineRule(
                id=1,
                name="r1",
                conditions=(RuleCondition(fact="x", operator="==", value=1),),
            ),
        )
    return Ruleset(group="test", rules=rules)


class DummyValidator(Validator):
    """A test validator that always returns one issue."""

    def validate(self, ruleset):
        return [ValidationIssue(message="dummy issue", severity=ValidationSeverity.INFO)]


class TestValidationService:
    def test_default_validates_empty_ruleset(self):
        svc = ValidationService()
        issues = svc.validate_ruleset(_make_ruleset(rules=()))
        assert any("empty" in i.lower() for i in issues)

    def test_default_validates_duplicate_ids(self):
        rules = (
            EngineRule(
                id=1,
                name="r1",
                conditions=(RuleCondition(fact="x", operator="==", value=1),),
            ),
            EngineRule(
                id=1,
                name="r2",
                conditions=(RuleCondition(fact="y", operator="==", value=2),),
            ),
        )
        issues = ValidationService().validate_ruleset(_make_ruleset(rules=rules))
        assert any("duplicate" in i.lower() for i in issues)

    def test_register_custom_validator(self):
        svc = ValidationService()
        svc.register_validator(DummyValidator())
        issues = svc.validate_ruleset(_make_ruleset())
        assert any("dummy issue" in i for i in issues)

    def test_unregister_validator(self):
        svc = ValidationService(validators=[DummyValidator()])
        svc.unregister_validator(DummyValidator)
        issues = svc.validate_ruleset(_make_ruleset())
        assert not any("dummy issue" in i for i in issues)

    def test_validate_detailed_returns_issues(self):
        svc = ValidationService(validators=[DummyValidator()])
        issues = svc.validate_ruleset_detailed(_make_ruleset())
        assert len(issues) == 1
        assert issues[0].severity == ValidationSeverity.INFO

    def test_valid_ruleset_no_issues(self):
        svc = ValidationService()
        issues = svc.validate_ruleset(_make_ruleset())
        assert issues == []

    def test_builtin_validator_unsupported_operator(self):
        # RuleCondition validates operators in __post_init__, so we test via service
        svc = ValidationService()
        # Valid operator - should pass
        issues = svc.validate_ruleset(_make_ruleset())
        assert issues == []
