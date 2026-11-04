"""Shared condition comparison helpers for engine evaluators.

This module centralizes operator evaluation so the PHREAK engine, the reference
evaluator, and any custom engine all follow the same hardening flags and
semantics. Defaults preserve current behavior unless strict flags are enabled.
"""

from __future__ import annotations

import logging
import operator
import re
from collections.abc import Callable
from decimal import Decimal
from typing import Any

from fluxrules.domain.comparison_issues import ComparisonIssue, type_label
from fluxrules.engine import uncomparable
from fluxrules.engine.uncomparable import Uncomparable
from fluxrules.utils.metrics import get_metrics

logger = logging.getLogger(__name__)

VALID_OPERATORS: frozenset[str] = frozenset(
    {
        # Canonical names
        "eq",
        "ne",
        "gt",
        "gte",
        "lt",
        "lte",
        # Symbol aliases
        "==",
        "!=",
        ">",
        ">=",
        "<",
        "<=",
        # Collection / string operators
        "in",
        "not_in",
        "contains",
        "not_contains",
        "starts_with",
        "ends_with",
        "regex",
    }
)

# Canonical word-aliases normalized to their symbolic equivalents so the shared
# evaluator honours every operator accepted by ``VALID_OPERATORS``. Without this
# a validator-approved ``gt`` (etc.) would silently fall through and return
# ``False`` in PHREAK/Beta.
_ALIAS_TO_SYMBOL: dict[str, str] = {
    "eq": "==",
    "ne": "!=",
    "gt": ">",
    "gte": ">=",
    "lt": "<",
    "lte": "<=",
}

# The comparison behind each symbolic operator. The engine operator and the
# alpha prefilter both call these, so they cannot drift apart.
COMPARISONS: dict[str, Callable[[Any, Any], Any]] = {
    "==": operator.eq,
    "!=": operator.ne,
    ">": operator.gt,
    ">=": operator.ge,
    "<": operator.lt,
    "<=": operator.le,
}
ORDERING_OPS: frozenset[str] = frozenset({">", ">=", "<", "<="})

# ``in`` / ``not_in`` test membership of a list of values. A single value is a
# one-item list, never a container to search: ``"U"`` is not a member of
# ``"US"``. The engine operator, the alpha prefilter and the rule-time
# normalisation all use these helpers, so every path agrees.
MEMBERSHIP_OPS: frozenset[str] = frozenset({"in", "not_in"})
_MEMBERSHIP_COLLECTIONS = (list, tuple, set, frozenset)


def is_membership_collection(value: Any) -> bool:
    """True when *value* is a list of members (list, tuple, set or frozenset)."""
    return isinstance(value, _MEMBERSHIP_COLLECTIONS)


def as_membership_collection(value: Any) -> Any:
    """Return *value* if it is a list of members, otherwise a one-item tuple."""
    return value if is_membership_collection(value) else (value,)


def _coerce_bool_string(value: Any, enabled: bool) -> Any:
    if not enabled or not isinstance(value, str):
        return value
    lowered = value.strip().lower()
    if lowered == "true":
        return True
    if lowered == "false":
        return False
    return value


def coerce_bool_string(value: Any) -> Any:
    """Read ``"true"`` / ``"false"`` (any case, surrounding spaces) as booleans.

    This is what ``boolean_string_coercion`` does to each side of a comparison.
    Anything else, including a list, is returned unchanged.
    """
    return _coerce_bool_string(value, True)


def is_plain_number(value: Any) -> bool:
    """An ``int`` or ``float`` that is not a ``bool``: what strict types can order."""
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _strict_type_compatible(op: str, left: Any, right: Any) -> bool:
    if op in ORDERING_OPS:
        return is_plain_number(left) and is_plain_number(right)

    if op in {"==", "!="}:
        # Allow exact-type comparisons or int/float interop (excluding bool).
        if isinstance(left, bool) or isinstance(right, bool):
            return isinstance(left, bool) and isinstance(right, bool)
        if is_plain_number(left) and is_plain_number(right):
            return True
        return type(left) is type(right)

    return True


def is_nan(value: Any) -> bool:
    """A float or ``Decimal`` NaN, which cannot be ordered."""
    if isinstance(value, float):
        return value != value
    return isinstance(value, Decimal) and value.is_nan()


# Why a comparison could not be made. Fixed strings, so every evaluation path
# reports the same reason for the same case.
REASON_NONE = "None cannot be ordered"
REASON_NAN = "NaN cannot be ordered"
REASON_STRICT = "strict_type_comparison orders two numbers only"
REASON_ORDER = "these types cannot be ordered"
REASON_CONTAINS = "the fact value cannot contain the rule value"
REASON_MEMBERSHIP = "the fact value cannot be looked up in the rule's values"
REASON_REGEX = "the rule value is not a valid regular expression"


def _uncomparable(field: str, op: str, left: Any, right: Any, reason: str) -> Uncomparable:
    uncomparable.note()
    return Uncomparable(ComparisonIssue(field, op, type_label(left), type_label(right), reason))


def _failure_reason(op: str, left: Any, right: Any, exc: Exception) -> str:
    if op in ORDERING_OPS:
        if left is None or right is None:
            return REASON_NONE
        if is_nan(left) or is_nan(right):
            return REASON_NAN
        if isinstance(exc, TypeError):
            return REASON_ORDER
    elif op in ("contains", "not_contains") and isinstance(exc, TypeError):
        return REASON_CONTAINS
    elif op in MEMBERSHIP_OPS and isinstance(exc, TypeError):
        return REASON_MEMBERSHIP
    elif op == "regex" and isinstance(exc, re.error):
        return REASON_REGEX
    return f"the comparison raised {type(exc).__name__}"


def compare_operator(
    op: str,
    event_value: Any,
    rule_value: Any,
    *,
    field_present: bool,
    strict_null_handling: bool,
    strict_type_comparison: bool,
    boolean_string_coercion: bool,
    emit_metrics: bool = True,
    field: str = "",
) -> bool | Uncomparable:
    """Evaluate a single operator: ``True``, ``False`` or :class:`Uncomparable`.

    A comparison with no answer returns a falsy :class:`Uncomparable` holding
    its issue, and is counted (see :mod:`fluxrules.engine.uncomparable`). It is
    reported (listed, warned about or raised) once per rule, when it leaves the
    rule undecided. These have no answer:

    - ordering (``>``, ``>=``, ``<``, ``<=``) with ``None`` or ``NaN`` on either
      side, or with types Python cannot order (``"abc" > 5``, a ``date``
      against a ``datetime``);
    - ordering two values that are not both numbers, under
      ``strict_type_comparison``;
    - ``contains`` / ``not_contains``, ``in`` / ``not_in`` or ``regex`` that
      raise (a number has no contents, a pattern does not compile).

    ``==`` and ``!=`` always have an answer: values that differ, including
    ``None``, ``NaN`` and values of different types, are not equal.

    *field* names the fact field in the reported issue.
    """
    # Normalize canonical word-aliases (eq/ne/gt/gte/lt/lte) to symbols so a
    # single code path implements them for every engine sharing this evaluator.
    op = _ALIAS_TO_SYMBOL.get(op, op)

    if not field_present:
        return False

    if event_value is None:
        if strict_null_handling:
            if emit_metrics:
                get_metrics().increment_comparison_metric("strict_null_evaluations")
            if op == "==":
                return rule_value is None
            if op == "!=":
                return rule_value is not None
        if op in ORDERING_OPS:
            return _uncomparable(field, op, None, rule_value, REASON_NONE)
        return False

    left = _coerce_bool_string(event_value, boolean_string_coercion)
    right = _coerce_bool_string(rule_value, boolean_string_coercion)
    left_changed = (left != event_value) or (type(left) is not type(event_value))
    right_changed = (right != rule_value) or (type(right) is not type(rule_value))
    if boolean_string_coercion and (left_changed or right_changed):
        if emit_metrics:
            get_metrics().increment_comparison_metric("string_bool_coercions")

    if strict_type_comparison and not _strict_type_compatible(op, left, right):
        if emit_metrics:
            get_metrics().increment_comparison_metric("comparison_type_mismatch")
        logger.debug(
            "Strict type mismatch blocked comparison: op=%s left=%r (%s) right=%r (%s)",
            op,
            left,
            type(left).__name__,
            right,
            type(right).__name__,
        )
        if op in ORDERING_OPS:
            reason = REASON_NONE if right is None else REASON_STRICT
            return _uncomparable(field, op, left, right, reason)
        # Values of different types are never equal.
        return op == "!="

    try:
        compare = COMPARISONS.get(op)
        if compare is not None:
            if compare(left, right):
                return True
            # Ordering NaN is always False, so only a False result needs the
            # NaN test; an int is never NaN, so its class skips the call.
            if op in ORDERING_OPS and (
                (left.__class__ is not int and is_nan(left))
                or (right.__class__ is not int and is_nan(right))
            ):
                return _uncomparable(field, op, left, right, REASON_NAN)
            return False
        if op == "in":
            return left in as_membership_collection(right)
        if op == "not_in":
            return left not in as_membership_collection(right)
        if op == "contains":
            return right in left
        if op == "not_contains":
            return right not in left
        if op == "starts_with":
            return str(left).startswith(str(right))
        if op == "ends_with":
            return str(left).endswith(str(right))
        if op == "regex":
            return bool(re.search(str(right), str(left)))
        return False
    except Exception as exc:
        logger.debug(
            "compare_operator could not compare: op=%r left=%r right=%r",
            op,
            event_value,
            rule_value,
            exc_info=True,
        )
        return _uncomparable(field, op, left, right, _failure_reason(op, left, right, exc))


def evaluate_operator(
    op: str,
    event_value: Any,
    rule_value: Any,
    *,
    field_present: bool,
    strict_null_handling: bool,
    strict_type_comparison: bool,
    boolean_string_coercion: bool,
    emit_metrics: bool = True,
    field: str = "",
) -> bool:
    """Evaluate a single operator with optional strict hardening.

    Like :func:`compare_operator`, but a comparison with no answer is
    ``False``.
    """
    return (
        compare_operator(
            op,
            event_value,
            rule_value,
            field_present=field_present,
            strict_null_handling=strict_null_handling,
            strict_type_comparison=strict_type_comparison,
            boolean_string_coercion=boolean_string_coercion,
            emit_metrics=emit_metrics,
            field=field,
        )
        is True
    )
