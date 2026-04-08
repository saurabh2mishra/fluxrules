"""Shared condition comparison helpers for engine evaluators.

This module centralizes operator evaluation so the simple engine, optimized
engine, and RETE network all follow the same hardening flags and semantics.
Defaults preserve current behavior unless strict flags are enabled.
"""

from __future__ import annotations

import re
from typing import Any
import logging

from app.utils.metrics import increment_comparison_metric

logger = logging.getLogger(__name__)


def _coerce_bool_string(value: Any, enabled: bool) -> Any:
    if not enabled or not isinstance(value, str):
        return value
    lowered = value.strip().lower()
    if lowered == "true":
        return True
    if lowered == "false":
        return False
    return value


def _is_numeric_non_bool(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _strict_type_compatible(op: str, left: Any, right: Any) -> bool:
    if op in {">", ">=", "<", "<="}:
        return _is_numeric_non_bool(left) and _is_numeric_non_bool(right)

    if op in {"==", "!="}:
        # Allow exact-type comparisons or int/float interop (excluding bool).
        if isinstance(left, bool) or isinstance(right, bool):
            return isinstance(left, bool) and isinstance(right, bool)
        if _is_numeric_non_bool(left) and _is_numeric_non_bool(right):
            return True
        return type(left) is type(right)

    return True


def evaluate_operator(
    op: str,
    event_value: Any,
    rule_value: Any,
    *,
    field_present: bool,
    strict_null_handling: bool,
    strict_type_comparison: bool,
    boolean_string_coercion: bool,
) -> bool:
    """Evaluate a single operator with optional strict hardening."""
    if not field_present:
        return False

    if event_value is None:
        if strict_null_handling:
            increment_comparison_metric("strict_null_evaluations")
            if op == "==":
                return rule_value is None
            if op == "!=":
                return rule_value is not None
        return False

    left = _coerce_bool_string(event_value, boolean_string_coercion)
    right = _coerce_bool_string(rule_value, boolean_string_coercion)
    left_changed = (left != event_value) or (type(left) is not type(event_value))
    right_changed = (right != rule_value) or (type(right) is not type(rule_value))
    if boolean_string_coercion and (left_changed or right_changed):
        increment_comparison_metric("string_bool_coercions")

    if strict_type_comparison and not _strict_type_compatible(op, left, right):
        increment_comparison_metric("comparison_type_mismatch")
        logger.debug(
            "Strict type mismatch blocked comparison: op=%s left=%r (%s) right=%r (%s)",
            op,
            left,
            type(left).__name__,
            right,
            type(right).__name__,
        )
        return False

    try:
        if op == ">":
            return left > right
        if op == ">=":
            return left >= right
        if op == "<":
            return left < right
        if op == "<=":
            return left <= right
        if op == "==":
            return left == right
        if op == "!=":
            return left != right
        if op == "in":
            return left in right
        if op == "not_in":
            return left not in right
        if op == "contains":
            return right in left
        if op == "starts_with":
            return str(left).startswith(str(right))
        if op == "ends_with":
            return str(left).endswith(str(right))
        if op == "regex":
            return bool(re.match(str(right), str(left)))
        return False
    except Exception:
        return False
