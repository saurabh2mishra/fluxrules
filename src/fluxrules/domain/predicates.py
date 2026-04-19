"""Predicate operator semantics used by engine implementations."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from fluxrules.domain.errors import UnknownOperatorError

Predicate = Callable[[Any, Any], bool]


OPERATORS: dict[str, Predicate] = {
    "eq": lambda left, right: left == right,
    "ne": lambda left, right: left != right,
    "gt": lambda left, right: left > right,
    "gte": lambda left, right: left >= right,
    "lt": lambda left, right: left < right,
    "lte": lambda left, right: left <= right,
    "in": lambda left, right: left in right,
    "contains": lambda left, right: right in left,
}


def evaluate_operator(operator: str, left: Any, right: Any) -> bool:
    predicate = OPERATORS.get(operator)
    if predicate is None:
        raise UnknownOperatorError(f"Operator '{operator}' is not supported")
    return predicate(left, right)
