"""Tests for the single-fact boundary guardrail (P0.3).

Verifies ``.research/PHREAK_P0_PLAN_TRUST_FOUNDATION.md`` task P0.3:

- Cross-fact / temporal rule shapes are detected.
- Warn by default; raise under ``strict=True`` / ``strict_scope=True``.
- Supported single-fact rules (incl. threshold ``accumulate``) are not rejected.
"""

from __future__ import annotations

import logging

import pytest

from fluxrules import Rule
from fluxrules.engine.infrastructure.scope_guard import (
    FindingKind,
    UnsupportedRuleShapeError,
    check_condition,
    enforce_single_fact_boundary,
)
from fluxrules.engine.phreak import PhreakEngine


def _leaf(field="amount", op=">", value=100):
    return {"type": "condition", "field": field, "op": op, "value": value}


class TestScopeGuardDetection:
    def test_plain_leaf_has_no_findings(self):
        assert check_condition(1, _leaf()) == []

    def test_and_of_leaves_has_no_findings(self):
        cond = {"type": "and", "conditions": [_leaf("a"), _leaf("b")]}
        assert check_condition(1, cond) == []

    def test_cross_fact_join_is_unsupported(self):
        cond = {"type": "join", "conditions": [_leaf("a"), _leaf("b")]}
        findings = check_condition(7, cond)
        assert any(f.kind is FindingKind.UNSUPPORTED for f in findings)
        assert findings[0].rule_id == 7

    def test_temporal_window_is_unsupported(self):
        cond = {"type": "sliding_window", "condition": _leaf("ts")}
        findings = check_condition(1, cond)
        assert any(f.kind is FindingKind.UNSUPPORTED for f in findings)

    def test_accumulate_over_collection_is_unsupported(self):
        cond = {
            "type": "accumulate",
            "source": "orders",
            "field": "total",
            "op": ">=",
            "threshold": 1000,
        }
        findings = check_condition(1, cond)
        assert any(f.kind is FindingKind.UNSUPPORTED for f in findings)

    def test_single_field_accumulate_is_a_note_not_error(self):
        cond = {"type": "accumulate", "field": "total", "op": ">=", "threshold": 10}
        findings = check_condition(1, cond)
        assert findings
        assert all(f.kind is FindingKind.SINGLE_FACT_NOTE for f in findings)

    def test_nested_unsupported_is_found(self):
        cond = {
            "type": "and",
            "conditions": [_leaf("a"), {"type": "temporal", "condition": _leaf("b")}],
        }
        findings = check_condition(1, cond)
        assert any(f.node_type == "temporal" for f in findings)


# --- P3 Track A: structural cross-fact detection -------------------------------

# Each entry: (label, condition_dsl, expected_unsupported_node_type | None).
# ``None`` means the shape must stay clean (no UNSUPPORTED finding) - these are
# the negative cases that guard against false positives.
_TRACK_A_CASES = [
    # --- A.1 multiple bindings / entities -> "multi_binding" ---
    (
        "two_bindings",
        {
            "type": "and",
            "conditions": [
                {
                    "type": "condition",
                    "field": "amount",
                    "op": ">",
                    "value": 1,
                    "bind": "o",
                },
                {
                    "type": "condition",
                    "field": "country",
                    "op": "==",
                    "value": "US",
                    "bind": "c",
                },
            ],
        },
        "multi_binding",
    ),
    (
        "two_entities",
        {
            "type": "and",
            "conditions": [
                {
                    "type": "condition",
                    "field": "a",
                    "op": ">",
                    "value": 1,
                    "fact_type": "Order",
                },
                {
                    "type": "condition",
                    "field": "b",
                    "op": ">",
                    "value": 1,
                    "fact_type": "Customer",
                },
            ],
        },
        "multi_binding",
    ),
    (
        "single_binding_ok",
        {
            "type": "and",
            "conditions": [
                {"type": "condition", "field": "a", "op": ">", "value": 1, "bind": "o"},
                {"type": "condition", "field": "b", "op": ">", "value": 1, "bind": "o"},
            ],
        },
        None,
    ),
    # --- A.2 cross-entity dotted fields -> "cross_entity_fields" ---
    (
        "cross_entity_dotted",
        {
            "type": "and",
            "conditions": [
                {"type": "condition", "field": "order.amount", "op": ">", "value": 1},
                {
                    "type": "condition",
                    "field": "customer.tier",
                    "op": "==",
                    "value": "gold",
                },
            ],
        },
        "cross_entity_fields",
    ),
    (
        "same_entity_dotted_ok",
        {
            "type": "and",
            "conditions": [
                {"type": "condition", "field": "order.amount", "op": ">", "value": 1},
                {
                    "type": "condition",
                    "field": "order.country",
                    "op": "==",
                    "value": "US",
                },
            ],
        },
        None,
    ),
    # --- A.2 field-to-field comparison -> "cross_field_ref" ---
    (
        "explicit_rhs_field",
        {
            "type": "condition",
            "field": "order.country",
            "op": "!=",
            "rhs_field": "prior.country",
        },
        "cross_field_ref",
    ),
    (
        "structured_rhs_field",
        {"type": "condition", "field": "a", "op": "==", "value": {"field": "b"}},
        "cross_field_ref",
    ),
    (
        "literal_rhs_ok",
        {"type": "condition", "field": "a", "op": "==", "value": 100},
        None,
    ),
    (
        "string_literal_rhs_ok",
        {"type": "condition", "field": "a", "op": "==", "value": "US"},
        None,
    ),
    # --- A.3 temporal keys -> "temporal_key" ---
    (
        "within_key",
        {"type": "condition", "field": "ts", "op": ">", "value": 1, "within": "5m"},
        "temporal_key",
    ),
    (
        "window_ms_key",
        {
            "type": "condition",
            "field": "ts",
            "op": ">",
            "value": 1,
            "window_ms": 300000,
        },
        "temporal_key",
    ),
    (
        "no_temporal_key_ok",
        {"type": "condition", "field": "ts", "op": ">", "value": 1},
        None,
    ),
    # --- A.4 widened vocabulary -> node type echoed back ---
    ("aggregate_type", {"type": "aggregate", "field": "x"}, "aggregate"),
    ("group_by_type", {"type": "group_by", "field": "x"}, "group_by"),
    ("correlate_type", {"type": "correlate", "conditions": []}, "correlate"),
    ("sequence_type", {"type": "sequence", "conditions": []}, "sequence"),
    ("followed_by_type", {"type": "followed_by", "conditions": []}, "followed_by"),
    ("during_type", {"type": "during", "condition": {"type": "condition"}}, "during"),
    ("every_type", {"type": "every", "condition": {"type": "condition"}}, "every"),
    (
        "not_exists_collection_type",
        {"type": "not_exists_collection", "condition": {"type": "condition"}},
        "not_exists_collection",
    ),
]


class TestTrackAStructuralDetection:
    """P3 Track A: catch cross-fact shapes a user actually writes."""

    @pytest.mark.parametrize(
        "case",
        _TRACK_A_CASES,
        ids=[c[0] for c in _TRACK_A_CASES],
    )
    def test_case(self, case):
        _label, cond, expected = case
        findings = check_condition(1, cond)
        unsupported = [f for f in findings if f.kind is FindingKind.UNSUPPORTED]
        if expected is None:
            assert unsupported == [], (
                f"expected no UNSUPPORTED finding, got {[f.node_type for f in unsupported]}"
            )
        else:
            assert any(f.node_type == expected for f in unsupported), (
                f"expected node_type '{expected}', got {[f.node_type for f in unsupported]}"
            )

    def test_plain_single_fact_rule_stays_clean(self):
        # A realistic single-fact rule must produce zero findings (no regression).
        cond = {
            "type": "and",
            "conditions": [
                _leaf("amount", ">", 100),
                {
                    "type": "or",
                    "conditions": [
                        _leaf("country", "==", "US"),
                        _leaf("country", "==", "CA"),
                    ],
                },
                {"type": "not", "condition": _leaf("blocked", "==", True)},
            ],
        }
        assert check_condition(1, cond) == []


class TestTrackAStrictIntegration:
    """Each new shape must fail fast under ``strict_scope=True`` at load time."""

    @pytest.mark.parametrize(
        "cond",
        [c[1] for c in _TRACK_A_CASES if c[2] is not None],
        ids=[c[0] for c in _TRACK_A_CASES if c[2] is not None],
    )
    def test_strict_raises_per_shape(self, cond):
        rule = Rule(
            id=1,
            name="bad",
            condition_dsl=cond,
            priority=0,
            domain="d",
            tags=frozenset(),
            persist=False,
        )
        engine = PhreakEngine(strict_scope=True)
        with pytest.raises(UnsupportedRuleShapeError):
            engine.load_rules([rule])


class TestEnforce:
    def test_warn_by_default_does_not_raise(self, caplog):
        rules = [
            {
                "id": 1,
                "condition_dsl": {
                    "type": "join",
                    "conditions": [_leaf("a"), _leaf("b")],
                },
            }
        ]
        with caplog.at_level(logging.WARNING):
            findings = enforce_single_fact_boundary(rules, strict=False)
        assert any(f.kind is FindingKind.UNSUPPORTED for f in findings)
        assert "single-fact boundary" in caplog.text

    def test_strict_raises_on_unsupported(self):
        rules = [{"id": 1, "condition_dsl": {"type": "window", "condition": _leaf("ts")}}]
        with pytest.raises(UnsupportedRuleShapeError):
            enforce_single_fact_boundary(rules, strict=True)

    def test_strict_does_not_raise_on_supported_rules(self):
        rules = [{"id": 1, "condition_dsl": _leaf()}]
        # Should return findings (empty) without raising.
        assert enforce_single_fact_boundary(rules, strict=True) == []


class TestEngineIntegration:
    def test_engine_warns_but_loads_by_default(self, caplog):
        rule = Rule(
            id=1,
            name="bad",
            condition_dsl={"type": "join", "conditions": [_leaf("a"), _leaf("b")]},
            priority=0,
            domain="d",
            tags=frozenset(),
            persist=False,
        )
        engine = PhreakEngine()  # strict_scope defaults to False
        with caplog.at_level(logging.WARNING):
            engine.load_rules([rule])
        assert "single-fact boundary" in caplog.text

    def test_engine_strict_scope_raises(self):
        rule = Rule(
            id=1,
            name="bad",
            condition_dsl={"type": "join", "conditions": [_leaf("a"), _leaf("b")]},
            priority=0,
            domain="d",
            tags=frozenset(),
            persist=False,
        )
        engine = PhreakEngine(strict_scope=True)
        with pytest.raises(UnsupportedRuleShapeError):
            engine.load_rules([rule])

    def test_engine_strict_scope_accepts_normal_rules(self):
        rules = [
            Rule(
                id=i,
                name=f"r{i}",
                condition_dsl=_leaf(field=f"f{i}", value=i),
                priority=0,
                domain="d",
                tags=frozenset(),
                persist=False,
            )
            for i in range(20)
        ]
        engine = PhreakEngine(strict_scope=True)
        engine.load_rules(rules)  # must not raise
        assert len(engine.rule_repository) == 20
