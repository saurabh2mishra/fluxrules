"""Predicate operator semantics used by the reference evaluator.

Every operator delegates to :func:`fluxrules.engine.operators.evaluate_operator`,
the same function ``PhreakEngine`` uses, with the comparison settings of the
process-wide config (``strict_null_handling``, ``strict_type_comparison`` and
``boolean_string_coercion``), read on every call as ``missing_field`` is. Keeping
a single implementation means ``evaluate()`` and ``PhreakEngine`` cannot drift
apart: a ``None`` value, a type mismatch or an invalid regex gives the same
answer on both paths, under the same settings.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from fluxrules.domain.errors import UnknownOperatorError
from fluxrules.engine.configuration import get_config
from fluxrules.engine.operators import VALID_OPERATORS, compare_operator
from fluxrules.engine.uncomparable import Uncomparable

Predicate = Callable[..., bool]


def compare(operator: str, left: Any, right: Any, *, field: str = "") -> bool | Uncomparable:
    """Like :func:`evaluate_operator`, but a comparison with no answer is an
    :class:`~fluxrules.engine.uncomparable.Uncomparable` (falsy) instead of
    ``False``."""
    if operator not in VALID_OPERATORS:
        raise UnknownOperatorError(f"Operator '{operator}' is not supported")
    config = get_config()
    return compare_operator(
        operator,
        left,
        right,
        field_present=True,
        strict_null_handling=config.strict_null_handling,
        strict_type_comparison=config.strict_type_comparison,
        boolean_string_coercion=config.boolean_string_coercion,
        field=field,
    )


def _predicate(op: str) -> Predicate:
    def _evaluate(left: Any, right: Any, *, field: str = "") -> bool:
        return compare(op, left, right, field=field) is True

    return _evaluate


OPERATORS: dict[str, Predicate] = {op: _predicate(op) for op in sorted(VALID_OPERATORS)}


def evaluate_operator(operator: str, left: Any, right: Any, *, field: str = "") -> bool:
    """Evaluate one operator under the process-wide comparison settings.

    *field* names the fact field in a reported
    :class:`~fluxrules.domain.comparison_issues.ComparisonIssue`.
    """
    predicate = OPERATORS.get(operator)
    if predicate is None:
        raise UnknownOperatorError(f"Operator '{operator}' is not supported")
    return predicate(left, right, field=field)
