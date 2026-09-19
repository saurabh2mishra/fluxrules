from fluxrules.domain import schemas
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
from fluxrules.domain.models import EvaluationResult, Fact, RuleCondition, Ruleset
from fluxrules.domain.unified_rule import Rule

__all__ = [
    "CorruptStoredRuleError",
    "CyclicDependencyError",
    "DSLValidationError",
    "EmptyRuleLogicError",
    "EvaluationResult",
    "Fact",
    # Error taxonomy - see fluxrules.domain.errors. Exported here because a
    # caller that cannot name the exception it must handle has no way to
    # handle it except by catching Exception.
    "FluxRulesError",
    "InvalidRuleError",
    "LossyConditionRebuildError",
    "LossyConditionViewWarning",
    "Rule",  # Pydantic-based Rule (primary pattern)
    "RuleCondition",
    "Ruleset",
    "UnknownOperatorError",
    "schemas",
]
