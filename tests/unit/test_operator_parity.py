"""Regression tests: every VALID_OPERATORS entry executes in the shared evaluator.

Audit 04 (C1) found that canonical word-aliases (eq/ne/gt/gte/lt/lte) and
``not_contains`` were accepted by ``VALID_OPERATORS`` / rule validation but had
no branch in ``engine.operators.evaluate_operator`` - so the shared evaluator
would
silently return ``False`` for a validator-approved rule. These tests pin the
fix: no accepted operator may silently fall through.
"""

from __future__ import annotations

import pytest

from fluxrules.engine.operators import VALID_OPERATORS, evaluate_operator

_DEFAULT_FLAGS = {
    "field_present": True,
    "strict_null_handling": False,
    "strict_type_comparison": False,
    "boolean_string_coercion": False,
    "emit_metrics": False,
}


# (operator, event_value, rule_value, expected)
_TRUE_CASES = [
    ("eq", 5, 5, True),
    ("==", 5, 5, True),
    ("ne", 5, 6, True),
    ("!=", 5, 6, True),
    ("gt", 6, 5, True),
    (">", 6, 5, True),
    ("gte", 5, 5, True),
    (">=", 5, 5, True),
    ("lt", 4, 5, True),
    ("<", 4, 5, True),
    ("lte", 5, 5, True),
    ("<=", 5, 5, True),
    ("in", "a", ["a", "b"], True),
    ("not_in", "z", ["a", "b"], True),
    ("contains", ["a", "b"], "a", True),
    ("not_contains", ["a", "b"], "z", True),
    ("starts_with", "hello", "he", True),
    ("ends_with", "hello", "lo", True),
    ("regex", "hello", "h.*o", True),
]


@pytest.mark.parametrize("op, event_value, rule_value, expected", _TRUE_CASES)
def test_operator_true_cases(op, event_value, rule_value, expected) -> None:
    assert evaluate_operator(op, event_value, rule_value, **_DEFAULT_FLAGS) is expected


def test_canonical_aliases_match_symbols() -> None:
    """Word aliases must behave identically to their symbolic counterparts."""
    pairs = [
        ("eq", "=="),
        ("ne", "!="),
        ("gt", ">"),
        ("gte", ">="),
        ("lt", "<"),
        ("lte", "<="),
    ]
    for alias, symbol in pairs:
        for a, b in [(5, 5), (5, 6), (6, 5)]:
            assert evaluate_operator(alias, a, b, **_DEFAULT_FLAGS) == evaluate_operator(
                symbol, a, b, **_DEFAULT_FLAGS
            )


def test_not_contains_false_case() -> None:
    assert evaluate_operator("not_contains", ["a", "b"], "a", **_DEFAULT_FLAGS) is False


def test_every_valid_operator_has_a_branch() -> None:
    """No accepted operator may silently fall through to the ``return False`` tail.

    We exercise each operator with values chosen to make it *true*; if an
    operator lacked a branch it would return ``False`` and fail here.
    """
    exercised = {case[0] for case in _TRUE_CASES}
    assert VALID_OPERATORS.issubset(exercised), (
        "Operators missing a positive test case (potential silent fall-through): "
        f"{sorted(VALID_OPERATORS - exercised)}"
    )
