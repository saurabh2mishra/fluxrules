"""Domain-specific error taxonomy with stable symbolic codes.

Every error here derives from :class:`FluxRulesError`, so a caller can catch
the whole family with one ``except`` clause, and each carries a stable ``code``
for logging and API responses that does not change when a message is reworded.

These names are part of the public API and are re-exported from
``fluxrules`` and ``fluxrules.domain``.
"""

from typing import Any

__all__ = [
    "ConditionValidationError",
    "CorruptStoredRuleError",
    "CyclicDependencyError",
    "EmptyRuleLogicError",
    "FactValidationError",
    "FieldNotFoundError",
    "FluxRulesError",
    "InvalidRuleError",
    "LossyConditionRebuildError",
    "LossyConditionViewWarning",
    "MissingFieldNotWarning",
    "UnknownFieldError",
    "UnknownOperatorError",
    "canonical_field_name",
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


class MissingFieldNotWarning(FutureWarning):
    """A NOT condition fired only because a field it tests was missing.

    Today a missing field makes its condition ``False``, so ``NOT`` over it is
    ``True`` and the rule fires: ``~(F("blocked") == True)`` matches a fact with
    no ``blocked`` key. From 2.0 a missing field will be *unknown* and such a
    ``NOT`` will not fire. Set ``EngineConfig(missing_field="unknown")`` to opt
    in now, or ``missing_field="false"`` to keep today's behaviour and silence
    this warning. To test for absence on purpose, use ``~F("x").exists()``.
    """

    code = "MISSING_FIELD_NOT"


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


_SEPARATORS = str.maketrans("", "", "_-. ")


def canonical_field_name(name: str) -> str:
    """Return the shape-insensitive form of a field name.

    Drops ``_``, ``-``, ``.`` and spaces and lowercases the rest, so
    ``userAge``, ``user_age``, ``user-age``, ``UserAge`` and ``userage`` all map
    to ``userage``. Two names with the same canonical form are the same field
    written in a different key style.
    """
    return name.translate(_SEPARATORS).lower()


def _unflattened_parent(field: str, facts: dict) -> str | None:
    """Return the parent key when *field* is a dotted path into a nested value.

    A rule on ``user.age`` can never match ``{"user": {"age": 30}}``: the engine
    reads flat keys only. When the first path segment is present and holds a
    mapping, the fact was not flattened, which is always a mistake.
    """
    if "." not in field:
        return None
    head = field.split(".", 1)[0]
    value = facts.get(head)
    if isinstance(value, dict) or hasattr(value, "keys"):
        return head
    return None


def is_field_typo(field: str, facts: dict) -> bool:
    """Return True when *field* is absent from *facts* but a present key is the
    same field written in another key style, or *field* points into a nested
    value that was never flattened.

    Key styles are compared through :func:`canonical_field_name`, so
    ``Amount`` / ``amount``, ``userAge`` / ``user_age`` and ``user-age`` all
    count. The comparison is exact equality after stripping separators and
    case, not a fuzzy match. Close-spelling (difflib) matching is deliberately
    NOT used to decide this: field families such as ``field_0`` / ``field_10``
    or ``line_1`` / ``line_2`` resemble each other closely, so a fuzzy match
    would raise on legitimately different fields in multi-schema or
    numbered-field rulesets. Fields that are genuinely absent with no
    look-alike present return False and evaluate to ``False`` as before. The
    human-facing "Did you mean" hint in :meth:`FieldNotFoundError.for_field`
    still uses difflib as a last resort, since a suggestion is advisory and
    never changes control flow.
    """
    if _unflattened_parent(field, facts) is not None:
        return True
    canonical = canonical_field_name(field)
    return any(canonical_field_name(str(k)) == canonical for k in facts)


class FieldNotFoundError(FluxRulesError):
    """Raised when a condition references a field that looks like a typo.

    A ``condition`` node whose field is not a key in the incoming fact dict
    previously returned ``False`` silently. When a present key is the same
    field in another key style (``Amount`` vs ``amount``, ``userAge`` vs
    ``user_age``), or the field is a dotted path into a nested value that was
    not flattened, this error is raised so the mismatch surfaces immediately.
    Fields with no look-alike present are treated as legitimately absent
    (different fact schema) and return ``False`` as before. The error message
    offers a "Did you mean" suggestion, which is advisory only and does not
    affect whether it is raised.

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
        parent = _unflattened_parent(field, facts)
        if parent is not None:
            return cls(
                f"Field '{field}' not found in fact: '{parent}' holds a nested value. "
                "The engine reads flat keys only; flatten the fact first (for example "
                "with fluxrules.pipeline.transforms.Flatten, or pass a model and let "
                f"the engine flatten it). Available keys: {available}"
            )
        canonical = canonical_field_name(field)
        same_shape = [k for k in available if canonical_field_name(k) == canonical]
        close = same_shape or difflib.get_close_matches(field, available, n=1, cutoff=0.6)
        hint = f" Did you mean '{close[0]}'?" if close else ""
        return cls(f"Field '{field}' not found in fact.{hint} Available keys: {available}")


class UnknownFieldError(InvalidRuleError, AttributeError):
    """Raised when a rule references a field the declared fact schema lacks.

    Checked once, when rules are loaded into an engine built with
    ``fact_schema=``, or when a field is read from :func:`fluxrules.facts.fields`.
    A rule that names a field the schema does not have can never match, so it
    is refused up front instead of evaluating to ``False`` on every fact.

    Also an :class:`AttributeError`, so ``fields(Model).typo`` behaves like any
    other missing attribute (``hasattr`` and ``getattr`` defaults work).
    """

    code = "UNKNOWN_FACT_FIELD"

    @classmethod
    def for_field(
        cls,
        field: str,
        schema_name: str,
        known: "list[str] | tuple[str, ...]",
        *,
        rule: str | None = None,
    ) -> "UnknownFieldError":
        """Build the error with a 'did you mean' hint drawn from the schema."""
        import difflib

        canonical = canonical_field_name(field)
        same_shape = [k for k in known if canonical_field_name(k) == canonical]
        close = same_shape or difflib.get_close_matches(field, list(known), n=1, cutoff=0.6)
        hint = f" Did you mean '{close[0]}'?" if close else ""
        where = f"Rule '{rule}' references" if rule else "Reference to"
        return cls(
            f"{where} unknown field '{field}' (not in fact schema {schema_name}).{hint} "
            f"Known fields: {sorted(known)}"
        )


class FactValidationError(FluxRulesError, ValueError):
    """Raised when a fact fails validation against the engine's ``fact_schema``.

    Only raised when the engine was built with ``validate_facts`` set to
    ``"normalize"`` or ``"strict"`` and ``on_invalid="raise"`` (the default).

    Attributes:
        schema_name: Name of the schema the fact was validated against.
        errors: The validator's error list (for Pydantic, ``ValidationError.errors()``),
            each entry carrying the field location and an error code.
    """

    code = "FACT_VALIDATION_ERROR"

    def __init__(self, schema_name: str, errors: "list[Any]") -> None:
        self.schema_name = schema_name
        self.errors = errors
        details = "; ".join(
            f"{'.'.join(str(p) for p in e.get('loc', ())) or '<root>'}: {e.get('msg', 'invalid')}"
            for e in errors
        )
        super().__init__(f"Fact failed validation against {schema_name}: {details}")


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
