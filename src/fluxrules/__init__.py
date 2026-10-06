"""Public package interface for fluxrules core.

Main API Functions:
    evaluate() - Evaluate rules against facts
    validate() - Validate rules
    explain() - Get explanation for execution

Every evaluation path returns the one :class:`EvaluationResult` type, whose
``fired_rules`` holds the rules that matched::

    from fluxrules import Rule, evaluate

    rule = Rule(
        name="adult",
        condition_dsl={"type": "condition", "field": "age", "op": ">=", "value": 18},
        action="allow",
    )
    evaluate(rule, {"age": 30}).fired_rules

For engine implementations, import directly from their packages:
    from fluxrules.engine.phreak import PhreakEngine

Infrastructure:
    from fluxrules.engine import BaseEngine
"""

from collections.abc import Iterable
from typing import Any

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
from fluxrules.domain.models import EngineRule as _EngineRule
from fluxrules.domain.models import EvaluationResult, Ruleset
from fluxrules.domain.rule_builder import ConditionBuilder, RuleBuilder
from fluxrules.domain.unified_rule import Rule
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


#: What :func:`evaluate` and :func:`validate` accept: one rule, several rules,
#: or an already-built :class:`Ruleset`.
Rules = Ruleset | Rule | Iterable[Rule]


def _coerce_facts(facts: object) -> dict[str, Any]:
    """Return *facts* as a plain dict, accepting Pydantic models too."""
    if isinstance(facts, dict):
        return facts
    if hasattr(facts, "model_dump"):  # Pydantic v2
        return facts.model_dump()
    if hasattr(facts, "dict"):  # Pydantic v1
        return facts.dict()
    raise TypeError(
        f"facts must be a dict or a Pydantic model, got {type(facts).__name__}. "
        "Convert your object to a dict first."
    )


def _as_ruleset(rules: Rules, *, group: str = "default") -> Ruleset:
    """Normalise whatever the caller passed into a :class:`Ruleset`.

    A ``Ruleset`` passes through. A single :class:`Rule` or an iterable of them
    is converted here, so callers never have to reach for the internal
    ``to_engine_rule()`` adapter just to evaluate a list of rules.
    """
    if isinstance(rules, Ruleset):
        return rules
    if isinstance(rules, Rule):
        rules = [rules]

    engine_rules: list[_EngineRule] = []
    for rule in rules:
        if isinstance(rule, Rule):
            engine_rules.append(rule.to_engine_rule())
        elif isinstance(rule, _EngineRule):
            engine_rules.append(rule)
        else:
            raise TypeError(
                "Expected a Rule, a Ruleset, or an iterable of Rules; got "
                f"{type(rule).__name__}. Build rules with fluxrules.Rule(...) "
                "or fluxrules.RuleBuilder."
            )
    return Ruleset(group=group, rules=tuple(engine_rules))


def evaluate(rules: Rules, facts: object) -> EvaluationResult:
    """Evaluate rules against a fact map with default in-memory services.

    *rules* may be a single :class:`Rule`, any iterable of them, or a
    :class:`Ruleset`::

        rule = Rule(name="adult", condition_dsl={...}, action="allow")
        result = evaluate(rule, {"age": 30})
        result.fired_rules  # the rules that matched

    *facts* may be a plain ``dict``, a Pydantic model, or any object with a
    ``model_dump()`` / ``dict()`` method.

    Returns:
        An :class:`EvaluationResult` whose ``fired_rules`` lists what matched.
    """
    result = _DEFAULT_SERVICE.evaluate_inline(_as_ruleset(rules), _coerce_facts(facts))
    _DEFAULT_SERVICE.execution_store.save(result)
    return result


def validate(rules: Rules) -> list[str]:
    """Validate rules and return human-readable issues.

    Accepts the same shapes as :func:`evaluate`. An empty list means valid.
    """
    return ValidationService().validate_ruleset(_as_ruleset(rules))


def explain(execution_id: str) -> dict[str, object]:
    """Return a transport-safe explanation payload for callers."""
    execution_result = _DEFAULT_SERVICE.explain(execution_id)
    return {
        "execution_id": execution_result.execution_id,
        "fired_rules": execution_result.fired_rules,
        "actions": execution_result.actions,
        "trace": execution_result.trace,
    }


__all__ = [
    "AuditService",
    "BaseEngine",
    "ConditionBuilder",
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
    "RuleBuilder",
    "RuleIDGenerator",
    "RulePersistencePort",
    "RuleService",
    "Rules",
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
