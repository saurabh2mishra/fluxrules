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
from fluxrules.engine.operators import VALID_OPERATORS
from fluxrules.engine.operators import evaluate_operator as _engine_evaluate_operator

Predicate = Callable[[Any, Any], bool]


def _predicate(op: str) -> Predicate:
    def _evaluate(left: Any, right: Any) -> bool:
        config = get_config()
        return _engine_evaluate_operator(
            op,
            left,
            right,
            field_present=True,
            strict_null_handling=config.strict_null_handling,
            strict_type_comparison=config.strict_type_comparison,
            boolean_string_coercion=config.boolean_string_coercion,
        )

    return _evaluate


OPERATORS: dict[str, Predicate] = {op: _predicate(op) for op in sorted(VALID_OPERATORS)}


def evaluate_operator(operator: str, left: Any, right: Any) -> bool:
    predicate = OPERATORS.get(operator)
    if predicate is None:
        raise UnknownOperatorError(f"Operator '{operator}' is not supported")
    return predicate(left, right)
