"""Comprehensive null handling tests to verify consistent behavior across engines.

Validates the null semantics documented in .github/NULL_HANDLING.md.
"""

from fluxrules.engine.operators import evaluate_operator


def _eval(op, event_value, rule_value, *, field_present=True):
    """Shorthand for evaluate_operator with strict null handling."""
    return evaluate_operator(
        op,
        event_value,
        rule_value,
        field_present=field_present,
        strict_null_handling=True,
        strict_type_comparison=False,
        boolean_string_coercion=False,
        emit_metrics=False,
    )


class TestNullHandlingComprehensive:
    """Verify null semantics per NULL_HANDLING.md."""

    # Equality
    def test_null_eq_null_is_true(self):
        assert _eval("==", None, None) is True

    def test_null_eq_value_is_false(self):
        assert _eval("==", None, 5) is False

    def test_null_ne_value_is_true(self):
        assert _eval("!=", None, 5) is True

    def test_null_ne_null_is_false(self):
        assert _eval("!=", None, None) is False

    # Ordering - null is never orderable
    def test_null_gt_is_false(self):
        assert _eval(">", None, 100) is False

    def test_null_gte_is_false(self):
        assert _eval(">=", None, 100) is False

    def test_null_lt_is_false(self):
        assert _eval("<", None, 100) is False

    def test_null_lte_is_false(self):
        assert _eval("<=", None, 100) is False

    # Collection
    def test_null_in_list_is_false(self):
        assert _eval("in", None, [1, 2, 3]) is False

    def test_null_not_in_list_is_false(self):
        # With strict null handling, null makes the whole comparison false
        assert _eval("not_in", None, [1, 2, 3]) is False

    # String operations
    def test_null_starts_with_is_false(self):
        assert _eval("starts_with", None, "prefix") is False

    def test_null_ends_with_is_false(self):
        assert _eval("ends_with", None, "suffix") is False

    # Missing field
    def test_missing_field_always_false(self):
        assert _eval("==", "value", "value", field_present=False) is False
        assert _eval(">", 10, 5, field_present=False) is False

    # Non-strict mode
    def test_non_strict_null_returns_false(self):
        result = evaluate_operator(
            ">",
            None,
            100,
            field_present=True,
            strict_null_handling=False,
            strict_type_comparison=False,
            boolean_string_coercion=False,
            emit_metrics=False,
        )
        assert result is False
