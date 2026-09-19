"""Public package interface for fluxrules core.

Main API Functions:
    evaluate() - Evaluate a ruleset against facts
    validate() - Validate a ruleset
    explain() - Get explanation for execution

For engine implementations, import directly from their packages:
    from fluxrules.engine.phreak import PhreakEngine

Infrastructure:
    from fluxrules.engine import BaseEngine
"""

from fluxrules.config.deployment import (
    ConfigValidationError,
    DeploymentConfig,
    DeploymentType,
)
from fluxrules.domain.errors import (
    CorruptStoredRuleError,
    CyclicDependencyError,
    DSLValidationError,
    EmptyRuleLogicError,
    FluxRulesError,
    InvalidRuleError,
    LossyConditionRebuildError,
    LossyConditionViewWarning,
    UnknownOperatorError,
)
from fluxrules.domain.models import EvaluationResult, Ruleset
from fluxrules.domain.unified_rule import Rule  # New unified Rule
from fluxrules.engine import (
    BaseEngine,
    get_available_engines,
    get_engine,
    register_engine,
    unregister_engine,
)
from fluxrules.engine.configuration import EngineConfig
from fluxrules.engine.operator_registry import OperatorRegistry, register_operator
from fluxrules.engine.phreak import PhreakEngine
from fluxrules.initialization import (
    initialize_fluxrules,
    initialize_persistence,
)
from fluxrules.ports.persistence import RulePersistencePort
from fluxrules.ports.validation import ValidationIssue, Validator
from fluxrules.services.audit_service import AuditService
from fluxrules.services.evaluation_service import EvaluationService
from fluxrules.services.persistence_service import PersistenceService
from fluxrules.services.rule_service import RuleService
from fluxrules.services.validation_service import ValidationService
from fluxrules.utils.id_generators import IDStrategy, RuleIDGenerator
from fluxrules.version import __version__

_DEFAULT_SERVICE = RuleService.create()


def evaluate(ruleset: Ruleset, facts: dict[str, object]) -> EvaluationResult:
    """Evaluate a ruleset against a fact map with default in-memory services.

    *facts* may be a plain ``dict``, a Pydantic model, or any object with a
    ``model_dump()`` / ``dict()`` method.
    """
    if hasattr(facts, "model_dump"):  # Pydantic v2
        facts = facts.model_dump()
    elif hasattr(facts, "dict"):  # Pydantic v1
        facts = facts.dict()
    elif not isinstance(facts, dict):
        raise TypeError(
            f"facts must be a dict or a Pydantic model, got {type(facts).__name__}. "
            "Convert your object to a dict first."
        )
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
    "AuditService",
    "BaseEngine",
    "ConfigValidationError",
    "CorruptStoredRuleError",
    # Error taxonomy (see fluxrules.domain.errors). Every one derives from
    # FluxRulesError, so `except FluxRulesError` catches the whole family.
    "CyclicDependencyError",
    "DSLValidationError",
    "DeploymentConfig",
    "DeploymentType",
    "EmptyRuleLogicError",
    "EngineConfig",
    "EvaluationResult",
    "EvaluationService",
    "FluxRulesError",
    "IDStrategy",
    "InvalidRuleError",
    "LossyConditionRebuildError",
    "LossyConditionViewWarning",
    "OperatorRegistry",
    "PersistenceService",
    "PhreakEngine",
    "Rule",
    "RuleIDGenerator",
    "RulePersistencePort",
    "RuleService",
    "Ruleset",
    "UnknownOperatorError",
    "ValidationIssue",
    "ValidationService",
    "Validator",
    "__version__",
    "evaluate",
    "explain",
    "get_available_engines",
    "get_engine",
    "initialize_fluxrules",
    "initialize_persistence",
    "register_engine",
    "register_operator",
    "unregister_engine",
    "validate",
]
