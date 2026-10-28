"""Domain-specific error taxonomy with stable symbolic codes.

Every error here derives from :class:`FluxRulesError`, so a caller can catch
the whole family with one ``except`` clause, and each carries a stable ``code``
for logging and API responses that does not change when a message is reworded.

These names are part of the public API and are re-exported from
``fluxrules`` and ``fluxrules.domain``.
"""

__all__ = [
    "ConditionValidationError",
    "CorruptStoredRuleError",
    "CyclicDependencyError",
    "EmptyRuleLogicError",
    "FieldNotFoundError",
    "FluxRulesError",
    "InvalidRuleError",
    "LossyConditionRebuildError",
    "LossyConditionViewWarning",
    "UnknownOperatorError",
    "is_field_typo",
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


class ConditionValidationError(InvalidRuleError):
    """Raised when DSL validation fails."""

    code = "DSL_VALIDATION_ERROR"


class CorruptStoredRuleError(FluxRulesError):
    """Raised when a persisted rule cannot be interpreted.

    ``rules.conditions`` is a JSON column holding exactly one shape: a DSL
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
    representation is always ``conditions``.
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
    original ``conditions``.
    """

    code = "LOSSY_CONDITION_REBUILD"


def is_field_typo(field: str, facts: dict) -> bool:
    """Return True when *field* is absent from *facts* but is a case variant of a
    present key (e.g. ``Amount`` vs ``amount``).

    Only a case-insensitive exact match counts as a typo, because it is
    unambiguous. Close-spelling (difflib) matching is deliberately NOT used to
    decide this: field families such as ``field_0`` / ``field_10`` or
    ``line_1`` / ``line_2`` resemble each other closely, so a fuzzy match would
    raise on legitimately different fields in multi-schema or numbered-field
    rulesets. Fields that are genuinely absent with no case-variant present
    return False and evaluate to ``False`` as before. The human-facing
    "Did you mean" hint in :meth:`FieldNotFoundError.for_field` still uses
    difflib, since a suggestion is advisory and never changes control flow.
    """
    lower = field.lower()
    return any(str(k).lower() == lower for k in facts)


class FieldNotFoundError(FluxRulesError):
    """Raised when a condition references a field that looks like a typo.

    A ``condition`` node whose field is not a key in the incoming fact dict
    previously returned ``False`` silently. When the absent field is a case
    variant of an existing key (e.g. ``Amount`` vs ``amount``), this error is
    raised so the typo surfaces immediately. Fields with no case-variant present
    are treated as legitimately absent (different fact schema) and return
    ``False`` as before. The error message still offers a difflib "Did you mean"
    suggestion, which is advisory only and does not affect whether it is raised.

    Use ``F("field").exists()`` when you intentionally want to test whether a
    field is present - that node always returns ``False`` for absent fields
    without raising.
    """

    code = "FIELD_NOT_FOUND"

    @classmethod
    def for_field(cls, field: str, facts: dict) -> "FieldNotFoundError":
        """Build the error with an available-keys list and a 'did you mean' hint."""
        import difflib

        available = sorted(str(k) for k in facts.keys())
        close = difflib.get_close_matches(field, available, n=1, cutoff=0.6)
        hint = f" Did you mean '{close[0]}'?" if close else ""
        return cls(f"Field '{field}' not found in fact.{hint} Available keys: {available}")


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
