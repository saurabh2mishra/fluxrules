"""Machine-checkable engine capability gate.

Audit 04 (L1) noted that CI runs all tests but has no explicit gate ensuring a
newly advertised operator cannot be added to ``VALID_OPERATORS`` (and thus to
validation/docs) without cross-engine execution coverage.

This module is that gate. It parameterizes **every** operator in
``VALID_OPERATORS`` and asserts it produces the expected result end-to-end
through the PHREAK engine. If someone adds a new operator to ``VALID_OPERATORS``
without wiring it into the shared evaluator, or without a positive case here,
this test fails.
"""

from __future__ import annotations

import pytest

from fluxrules import Rule
from fluxrules.engine.operators import VALID_OPERATORS
from fluxrules.engine.phreak import PhreakEngine

# operator -> (rule_value, matching_event_value, non_matching_event_value)
_OPERATOR_MATRIX: dict[str, tuple] = {
    "eq": (5, 5, 6),
    "==": (5, 5, 6),
    "ne": (5, 6, 5),
    "!=": (5, 6, 5),
    "gt": (5, 6, 4),
    ">": (5, 6, 4),
    "gte": (5, 5, 4),
    ">=": (5, 5, 4),
    "lt": (5, 4, 6),
    "<": (5, 4, 6),
    "lte": (5, 5, 6),
    "<=": (5, 5, 6),
    "in": (["a", "b"], "a", "z"),
    "not_in": (["a", "b"], "z", "a"),
    "contains": ("a", ["a", "b"], ["x", "y"]),
    "not_contains": ("z", ["a", "b"], ["z", "y"]),
    "starts_with": ("he", "hello", "world"),
    "ends_with": ("lo", "hello", "world"),
    "regex": ("h.*o", "hello", "world"),
}


def test_capability_matrix_covers_every_valid_operator() -> None:
    """No advertised operator may lack coverage in this gate."""
    missing = VALID_OPERATORS - set(_OPERATOR_MATRIX)
    assert not missing, (
        f"New operator(s) added to VALID_OPERATORS without a capability case: {sorted(missing)}"
    )


def _build_engine(cls, op, rule_value):
    engine = cls()
    engine.load_rules(
        [
            Rule(
                id=1,
                name=f"op_{op}",
                condition_dsl={
                    "type": "condition",
                    "field": "value",
                    "op": op,
                    "value": rule_value,
                },
                persist=False,
            )
        ]
    )
    return engine


@pytest.mark.parametrize("cls", [PhreakEngine])
@pytest.mark.parametrize("op", sorted(_OPERATOR_MATRIX))
def test_operator_executes_end_to_end(cls, op) -> None:
    rule_value, match_value, non_match_value = _OPERATOR_MATRIX[op]
    engine = _build_engine(cls, op, rule_value)

    assert engine.evaluate({"value": match_value}).fired_rules == [1], (
        f"{cls.__name__}: operator {op!r} did not fire on a matching fact"
    )
    assert engine.evaluate({"value": non_match_value}).fired_rules == [], (
        f"{cls.__name__}: operator {op!r} fired on a non-matching fact"
    )
