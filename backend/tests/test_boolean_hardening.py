from app.config import settings
from app.engine.comparison import evaluate_operator
from app.compiler.rule_compiler import CompiledConstraint
from app.validation._normalization import constraint_to_interval
from app.utils.metrics import get_dashboard_metrics


def test_default_mode_preserves_bool_numeric_equality_behavior():
    assert evaluate_operator(
        "==",
        True,
        1,
        field_present=True,
        strict_null_handling=False,
        strict_type_comparison=False,
        boolean_string_coercion=False,
    )


def test_strict_type_blocks_bool_numeric_equality():
    assert not evaluate_operator(
        "==",
        True,
        1,
        field_present=True,
        strict_null_handling=False,
        strict_type_comparison=True,
        boolean_string_coercion=False,
    )


def test_boolean_string_coercion_when_enabled():
    assert not evaluate_operator(
        "==",
        "TRUE",
        True,
        field_present=True,
        strict_null_handling=False,
        strict_type_comparison=False,
        boolean_string_coercion=False,
    )
    assert evaluate_operator(
        "==",
        "TRUE",
        True,
        field_present=True,
        strict_null_handling=False,
        strict_type_comparison=False,
        boolean_string_coercion=True,
    )


def test_strict_null_handling_supports_explicit_none_equality():
    assert not evaluate_operator(
        "==",
        None,
        None,
        field_present=True,
        strict_null_handling=False,
        strict_type_comparison=False,
        boolean_string_coercion=False,
    )
    assert evaluate_operator(
        "==",
        None,
        None,
        field_present=True,
        strict_null_handling=True,
        strict_type_comparison=False,
        boolean_string_coercion=False,
    )


def test_validation_bool_numeric_mode_toggle(monkeypatch):
    constraint = CompiledConstraint(field="is_active", operator="==", value=True)

    monkeypatch.setattr(settings, "VALIDATION_STRICT_BOOL_NUMERIC", False)
    assert constraint_to_interval(constraint) is not None

    monkeypatch.setattr(settings, "VALIDATION_STRICT_BOOL_NUMERIC", True)
    assert constraint_to_interval(constraint) is None


def test_strict_comparison_telemetry_counters_increment():
    before = get_dashboard_metrics()["strict_comparison"]

    evaluate_operator(
        "==",
        True,
        1,
        field_present=True,
        strict_null_handling=False,
        strict_type_comparison=True,
        boolean_string_coercion=False,
    )
    evaluate_operator(
        "==",
        "FALSE",
        False,
        field_present=True,
        strict_null_handling=False,
        strict_type_comparison=False,
        boolean_string_coercion=True,
    )
    evaluate_operator(
        "==",
        None,
        None,
        field_present=True,
        strict_null_handling=True,
        strict_type_comparison=False,
        boolean_string_coercion=False,
    )

    after = get_dashboard_metrics()["strict_comparison"]
    assert after["type_mismatch"] >= before["type_mismatch"] + 1
    assert after["string_bool_coercions"] >= before["string_bool_coercions"] + 1
    assert after["null_evaluations"] >= before["null_evaluations"] + 1
