"""Domain-specific error taxonomy with stable symbolic codes.

Every error here derives from :class:`FluxRulesError`, so a caller can catch
the whole family with one ``except`` clause, and each carries a stable ``code``
for logging and API responses that does not change when a message is reworded.

These names are part of the public API and are re-exported from
``fluxrules`` and ``fluxrules.domain``.
"""

from typing import Any

__all__ = [
    "ComparisonWarning",
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
    "MembershipValueWarning",
    "MissingFieldNotWarning",
    "RuleValueError",
    "RuleValueWarning",
    "UncomparableValuesError",
    "UnknownFieldError",
    "UnknownOperatorError",
    "YamlValueWarning",
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


class MembershipValueWarning(UserWarning):
    """An ``in`` / ``not_in`` condition was given a single value, not a list.

    ``F("country").isin("US")`` and ``{"op": "in", "value": "US"}`` mean "is
    one of these values", so the value should be a list. Given a plain string,
    Python's ``in`` would test for a substring instead, and ``"U"`` would
    count as a member of ``"US"``. FluxRules treats a single value as a
    one-item list (``"US"`` becomes ``["US"]``) on every evaluation path, and
    emits this warning so the author can write the list explicitly.
    """

    code = "MEMBERSHIP_VALUE_NOT_LIST"


class RuleValueWarning(UserWarning):
    """A rule's value does not suit its operator, so the rule can never match.

    ``>``, ``>=``, ``<`` and ``<=`` need a number, text, a date or a time;
    ``starts_with`` and ``ends_with`` need text; ``regex`` needs text that
    compiles. Emitted when the rule is created. The rule still loads and
    evaluates as before; :func:`fluxrules.validate` lists the same problems.
    """

    code = "RULE_VALUE_MISMATCH"


class RuleValueError(InvalidRuleError, ValueError):
    """A rule's value does not fit the type of its field in the fact schema.

    Checked when rules are loaded into an engine built with ``fact_schema=``.
    ``amount: float`` compared with the text ``"100.1"`` can never match, so
    the rules are refused, with a suggested fix.

    Attributes:
        field: the field the rule compares.
        rule: the rule's name, or its id, if known.
        schema_name: the fact schema's class name.
        value: the rule value.
        summary: the message, as one sentence.
    """

    code = "RULE_VALUE_TYPE"

    def __init__(
        self,
        summary: str,
        *,
        field: str | None = None,
        rule: str | None = None,
        schema_name: str | None = None,
        value: Any = None,
    ) -> None:
        super().__init__(summary)
        self.summary = summary
        self.field = field
        self.rule = rule
        self.schema_name = schema_name
        self.value = value

    def __reduce__(self) -> Any:
        return (
            _rebuild_rule_value_error,
            (self.summary, self.field, self.rule, self.schema_name, self.value),
        )


def _rebuild_rule_value_error(
    summary: str, field: Any, rule: Any, schema_name: Any, value: Any
) -> RuleValueError:
    return RuleValueError(summary, field=field, rule=rule, schema_name=schema_name, value=value)


class YamlValueWarning(UserWarning):
    """A YAML value is read as written, where FluxRules 1.1 read it differently.

    FluxRules reads YAML files by YAML 1.2's rules: only ``true`` and
    ``false`` are booleans, so ``NO`` is the text ``"NO"``; ``0755`` and
    ``1:30`` are text; ``1e3`` is the number 1000. FluxRules 1.1 read ``NO`` as
    ``False``, ``0755`` as 493, ``1:30`` as 90 and ``1e3`` as text. Emitted
    once per such value, naming the file and line.
    """

    code = "YAML_VALUE_READING"


class ComparisonWarning(UserWarning):
    """A comparison could not be made, so its condition was no match.

    ``"abc" > 5``, ``None > 5``, ``float("nan") > 5``, a ``date`` ordered
    against a ``datetime``, ``contains`` on a number and an invalid regex have
    no answer. The condition is no match, and ``NOT`` over it fires. Emitted
    once per field, operator and pair of types under the default
    ``EngineConfig(uncomparable=None)``. Set ``uncomparable="false"`` to
    silence it, ``"unknown"`` so ``NOT`` over such a comparison does not fire,
    or ``"raise"`` to raise :class:`UncomparableValuesError` instead.
    """

    code = "UNCOMPARABLE_VALUES"


class UncomparableValuesError(FluxRulesError, ValueError):
    """A comparison could not be made, under ``EngineConfig(uncomparable="raise")``.

    Attributes:
        issue: The :class:`~fluxrules.domain.comparison_issues.ComparisonIssue`
            naming the field, the operator, both types and the reason.
    """

    code = "UNCOMPARABLE_VALUES"

    def __init__(self, issue: Any) -> None:
        super().__init__(issue.describe())
        self.issue = issue

    def __reduce__(self) -> tuple[Any, ...]:
        # Rebuilt from the issue, so the error survives a worker process.
        return (type(self), (self.issue,))


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


# Word separators a key style may use. "." is not one of them: it separates
# levels of nesting, so "user.name" and "username" are different fields.
_SEPARATORS = str.maketrans("", "", "_- ")


def canonical_field_name(name: str, *, styles: bool = True) -> str:
    """Return the comparable form of a field name.

    With ``styles=True`` it drops ``_``, ``-`` and spaces and lowercases the
    rest, so ``userAge``, ``user_age``, ``user-age``, ``UserAge`` and
    ``userage`` all map to ``userage``: the same field in a different key
    style. With ``styles=False`` it only lowercases, so only case variants
    (``Amount`` / ``amount``) match. ``.`` is always kept, because it separates
    levels of nesting.
    """
    return (name.translate(_SEPARATORS) if styles else name).lower()


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


def is_field_typo(field: str, facts: dict, *, styles: bool = False) -> bool:
    """Return True when *field* is absent from *facts* but a present key is the
    same field spelled differently, or *field* points into a nested value that
    was never flattened.

    By default only case differs (``Amount`` / ``amount``). With
    ``styles=True`` key styles count too (``userAge`` / ``user_age`` /
    ``user-age``). Engines pass ``styles=True`` only when they have a fact
    schema: then every rule field is known to be real, so a look-alike key can
    only be a mismatch. Without a schema, one ruleset may serve several fact
    shapes that spell a field differently, and treating those as typos would
    reject valid facts. The comparison is exact equality through
    :func:`canonical_field_name`, not a fuzzy match. Close-spelling (difflib) matching is deliberately
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
    canonical = canonical_field_name(field, styles=styles)
    return any(canonical_field_name(str(k), styles=styles) == canonical for k in facts)


class FieldNotFoundError(FluxRulesError):
    """Raised when a condition references a field that looks like a typo.

    A ``condition`` node whose field is not a key in the incoming fact dict
    previously returned ``False`` silently. When a present key is the same
    field in another case (``Amount`` vs ``amount``), or in another key style
    when the engine has a fact schema (``userAge`` vs ``user_age``), or the
    field is a dotted path into a nested value that was not flattened, this
    error is raised so the mismatch surfaces immediately.
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

    # Set by ``for_field``: the unknown field, the rule naming it, the schema,
    # the suggested field (or None), and the message without the field list.
    field: str | None = None
    rule: str | None = None
    schema_name: str | None = None
    suggestion: str | None = None
    summary: str = ""

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
        summary = f"{where} unknown field '{field}' (not in fact schema {schema_name}).{hint}"
        error = cls(f"{summary} Known fields: {sorted(known)}")
        error.field = field
        error.rule = rule
        error.schema_name = schema_name
        error.suggestion = close[0] if close else None
        error.summary = summary
        return error

    @classmethod
    def for_parent(
        cls,
        field: str,
        schema_name: str,
        children: "list[str] | tuple[str, ...]",
        *,
        rule: str | None = None,
    ) -> "UnknownFieldError":
        """Build the error for a nested model named as if it were a field.

        A nested model is flattened into its own fields, so a fact never has a
        key for the model itself, and a rule on it could never match.
        """
        example = children[0] if children else f"{field}.<field>"
        where = f"Rule '{rule}' references" if rule else "Reference to"
        summary = (
            f"{where} '{field}', which is a nested model in fact schema {schema_name}, "
            f"not a field. Use one of its fields, such as '{example}'. To test whether "
            f"it is set, use F('{example}').exists()."
        )
        error = cls(summary)
        error.field = field
        error.rule = rule
        error.schema_name = schema_name
        error.suggestion = example if children else None
        error.summary = summary
        return error


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

    def __reduce__(self) -> tuple[Any, ...]:
        # Rebuild from the constructor arguments so the error survives pickling
        # (evaluate_batch sends it back from worker processes).
        return (type(self), (self.schema_name, self.errors))


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
