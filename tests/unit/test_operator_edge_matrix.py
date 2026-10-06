"""Operator edge-case matrix over the shared ``evaluate_operator``.

``test_capability_matrix`` proves every advertised operator has a *positive*
end-to-end case. This module pins the *edge* semantics that curated happy-path
tests miss, driving ``evaluate_operator`` directly with explicit hardening flags
so the expected result is unambiguous:

- missing field (``field_present=False``) -> always ``False``;
- ``None`` values under ``strict_null_handling`` on and off;
- type mismatches under ``strict_type_comparison`` on and off;
- ``boolean_string_coercion`` on and off;
- ``regex`` / ``starts_with`` on non-strings (coerced via ``str``);
- ``in`` / ``contains`` on non-collections (exception -> ``False``);
- word aliases resolving to their symbols.

Every accepted operator must return a ``bool`` and never raise.
"""

from __future__ import annotations

import pytest

from fluxrules.engine.operators import VALID_OPERATORS, evaluate_operator


def _ev(op, event, rule, **flags) -> bool:
    base = {
        "field_present": True,
        "strict_null_handling": False,
        "strict_type_comparison": False,
        "boolean_string_coercion": False,
        "emit_metrics": False,
    }
    base.update(flags)
    return evaluate_operator(op, event, rule, **base)


# (id, op, event_value, rule_value, flags, expected)
_CASES = [
    # Null handling
    ("null_eq_none_strict", "==", None, None, {"strict_null_handling": True}, True),
    ("null_eq_val_strict", "==", None, 5, {"strict_null_handling": True}, False),
    ("null_ne_val_strict", "!=", None, 5, {"strict_null_handling": True}, True),
    ("null_ne_none_strict", "!=", None, None, {"strict_null_handling": True}, False),
    ("null_gt_strict", ">", None, 5, {"strict_null_handling": True}, False),
    ("null_eq_none_lenient", "==", None, None, {}, False),
    ("null_eq_val_lenient", "==", None, 5, {}, False),
    # Type mismatch
    ("num_gt_str_lenient", ">", 5, "abc", {}, False),
    ("num_gt_str_strict", ">", 5, "abc", {"strict_type_comparison": True}, False),
    ("eq_int_str_lenient", "==", 5, "5", {}, False),
    ("eq_int_str_strict", "==", 5, "5", {"strict_type_comparison": True}, False),
    ("eq_int_float_strict", "==", 5, 5.0, {"strict_type_comparison": True}, True),
    ("gt_num_ok_strict", ">", 6, 5, {"strict_type_comparison": True}, True),
    # Boolean/string coercion
    ("coerce_true_on", "==", "true", True, {"boolean_string_coercion": True}, True),
    ("coerce_true_off", "==", "true", True, {}, False),
    ("coerce_false_on", "==", "false", False, {"boolean_string_coercion": True}, True),
    # Regex on strings and non-strings (re.search semantics: pattern may match anywhere)
    ("regex_match", "regex", "hello", "h.*o", {}, True),
    ("regex_no_match", "regex", "world", "h.*o", {}, False),
    ("regex_on_int", "regex", 12345, "12.*", {}, True),
    # partial match: pattern does NOT start at position 0 → must still match (re.search)
    ("regex_partial_match", "regex", "hello_world", "world", {}, True),
    ("regex_partial_digits", "regex", "abc1234def", r"\d{4}", {}, True),
    # starts_with / ends_with, incl. non-string coercion
    ("starts_with_str", "starts_with", "hello", "he", {}, True),
    ("ends_with_str", "ends_with", "hello", "lo", {}, True),
    ("starts_with_int", "starts_with", 12345, "12", {}, True),
    # in / not_in / contains / not_contains, incl. non-collections
    ("in_list", "in", "a", ["a", "b"], {}, True),
    ("in_noncollection", "in", 5, 3, {}, False),
    ("not_in_list", "not_in", "z", ["a", "b"], {}, True),
    ("contains_list", "contains", ["a", "b"], "a", {}, True),
    ("contains_noncollection", "contains", 5, 3, {}, False),
    ("not_contains_list", "not_contains", ["a", "b"], "z", {}, True),
    # Word aliases resolve to symbols
    ("alias_gt", "gt", 6, 5, {}, True),
    ("alias_lte_eq", "lte", 5, 5, {}, True),
    ("alias_ne", "ne", 5, 6, {}, True),
]


@pytest.mark.parametrize("case", _CASES, ids=[c[0] for c in _CASES])
def test_operator_edge_semantics(case) -> None:
    _id, op, event, rule, flags, expected = case
    assert _ev(op, event, rule, **flags) is expected


@pytest.mark.parametrize("op", sorted(VALID_OPERATORS))
def test_missing_field_never_matches(op: str) -> None:
    """No operator fires when its field is absent from the fact."""
    assert _ev(op, "anything", "anything", field_present=False) is False


@pytest.mark.parametrize("op", sorted(VALID_OPERATORS))
def test_operator_returns_bool_and_never_raises(op: str) -> None:
    """Every advertised operator is total: returns a bool for adversarial input."""
    # Deliberately mismatched types / non-collections across the board.
    for event, rule in ((5, "x"), ("x", 5), (None, []), ([1], 2), (1.5, {"k": 1})):
        result = _ev(op, event, rule)
        assert isinstance(result, bool)
