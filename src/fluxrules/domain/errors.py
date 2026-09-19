"""Domain-specific error taxonomy with stable symbolic codes.

Every error here derives from :class:`FluxRulesError`, so a caller can catch
the whole family with one ``except`` clause, and each carries a stable ``code``
for logging and API responses that does not change when a message is reworded.

These names are part of the public API and are re-exported from
``fluxrules`` and ``fluxrules.domain``.
"""

__all__ = [
    "CorruptStoredRuleError",
    "CyclicDependencyError",
    "DSLValidationError",
    "EmptyRuleLogicError",
    "FluxRulesError",
    "InvalidRuleError",
    "LossyConditionRebuildError",
    "LossyConditionViewWarning",
    "UnknownOperatorError",
]


class FluxRulesError(Exception):
    code = "FLUXRULES_ERROR"


class InvalidRuleError(FluxRulesError):
    code = "INVALID_RULE"


class UnknownOperatorError(FluxRulesError):
    code = "UNKNOWN_OPERATOR"


class CyclicDependencyError(FluxRulesError):
    """Raised when circular rule dependencies are detected."""

    code = "CYCLIC_DEPENDENCY"


class DSLValidationError(InvalidRuleError):
    """Raised when DSL validation fails."""

    code = "DSL_VALIDATION_ERROR"


class CorruptStoredRuleError(FluxRulesError):
    """Raised when a persisted rule cannot be interpreted.

    ``rules.condition_dsl`` is a JSON column holding exactly one shape: a DSL
    object. A row containing anything else was not written by this version and
    its intent cannot be recovered.

    This raises rather than degrading to an empty rule, because an empty rule
    matches nothing - and "matched nothing" is indistinguishable from a
    correct evaluation, so the corruption would never surface.
    """

    code = "CORRUPT_STORED_RULE"


class LossyConditionViewWarning(UserWarning):
    """A DSL tree could not be represented faithfully as a flat condition tuple.

    ``EngineRule.conditions`` (and ``Rule.conditions``) is a flat conjunction:
    it cannot express ``OR``, ``NOT`` or nesting. When such a node is
    flattened, the leaves are still returned, but the boolean structure is
    lost - so the view must not be used to decide rule logic. The canonical
    representation is always ``condition_dsl``.
    """

    code = "LOSSY_CONDITION_VIEW"


class LossyConditionRebuildError(InvalidRuleError):
    """Raised when a DSL tree would be rebuilt from a lossy condition view.

    Flattening ``OR(a, b)`` yields exactly the same leaves as ``AND(a, b)``.
    Rebuilding a tree from those leaves therefore emits an ``and`` node and
    silently narrows the rule: it now requires both conditions where it used
    to accept either, so it fires strictly less often. Nothing raises, the
    stored row is well-formed, and the rule looks correct in every listing -
    the failure only shows up as actions that never happened.

    The warning alone was not enough, because a warning does not stop the
    write. This refuses the conversion outright; callers must pass the
    original ``condition_dsl``.
    """

    code = "LOSSY_CONDITION_REBUILD"


class EmptyRuleLogicError(InvalidRuleError):
    """Raised when a rule would be stored with no condition logic at all.

    A rule with no conditions cannot do the one thing a rule is for. Storing
    it produces a row that looks entirely healthy - it has a name, a group, an
    action, and it loads without error - but can never fire. That is the worst
    failure shape available: silent, durable, and indistinguishable from a
    working rule until someone notices the actions never happened.

    This is raised at the persistence boundary rather than left to the caller,
    because by the time such a row exists the original logic is gone and
    cannot be reconstructed from the database.
    """

    code = "EMPTY_RULE_LOGIC"
