"""Public package interface for fluxrules core."""

from fluxrules.domain.models import EvaluationResult, Rule, Ruleset
from fluxrules.engine.interpreter import InterpreterEngine
from fluxrules.services.rule_service import RuleService
from fluxrules.services.validation_service import ValidationService
from fluxrules.version import __version__

_DEFAULT_SERVICE = RuleService.default()


def evaluate(ruleset: Ruleset, facts: dict[str, object]) -> EvaluationResult:
    """Evaluate a ruleset against a fact map with default in-memory services."""
    result = _DEFAULT_SERVICE.evaluate_inline(ruleset, facts)
    _DEFAULT_SERVICE.execution_store.save(result)
    return result


def validate(ruleset: Ruleset) -> list[str]:
    """Validate a ruleset and return human-readable issues."""
    return ValidationService().validate_ruleset(ruleset)


def explain(execution_id: str) -> dict[str, object]:
    """Return a transport-safe explanation payload for callers."""
    execution_result = _DEFAULT_SERVICE.explain(execution_id)
    return {
        "execution_id": execution_result.execution_id,
        "matched_rules": execution_result.matched_rule_ids,
        "actions": execution_result.actions,
        "trace": execution_result.trace,
    }


__all__ = [
    "__version__",
    "EvaluationResult",
    "Rule",
    "Ruleset",
    "InterpreterEngine",
    "RuleService",
    "evaluate",
    "validate",
    "explain",
]
