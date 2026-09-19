"""Tests for unified engine core infrastructure.

Covers: GlobalRuleRepository, SegmentNetwork, FieldIndex,
UnifiedWorkingMemory, TokenPropagator, Agenda, EvaluationFilter.
"""

from __future__ import annotations

import time

import pytest

from fluxrules import Rule
from fluxrules.engine.infrastructure.agenda import Agenda
from fluxrules.engine.infrastructure.evaluation_filter import EvaluationFilter
from fluxrules.engine.infrastructure.field_index import FieldIndex
from fluxrules.engine.infrastructure.global_rule_repository import (
    GlobalRuleRepository,
)
from fluxrules.engine.infrastructure.segment_network import (
    SegmentNetwork,
    _extract_fields,
)
from fluxrules.engine.infrastructure.token_propagator import TokenPropagator
from fluxrules.engine.infrastructure.working_memory import UnifiedWorkingMemory

# Fixtures


def _make_rule(
    rule_id: int,
    name: str = "",
    field: str = "amount",
    op: str = ">",
    value: int = 100,
    domain: str = "default",
    tags: frozenset[str] | None = None,
    priority: int = 0,
    action: str = "",
) -> Rule:
    return Rule(
        id=rule_id,
        name=name or f"rule_{rule_id}",
        condition_dsl={
            "type": "condition",
            "field": field,
            "op": op,
            "value": value,
        },
        action=action,
        priority=priority,
        domain=domain,
        tags=tags or frozenset(),
        persist=False,
    )


def _make_composite_rule(
    rule_id: int,
    fields: list[tuple[str, str, int]],
    logic: str = "AND",
    domain: str = "default",
    tags: frozenset[str] | None = None,
    priority: int = 0,
) -> Rule:
    conditions = [{"type": "condition", "field": f, "op": op, "value": v} for f, op, v in fields]
    return Rule(
        id=rule_id,
        name=f"rule_{rule_id}",
        condition_dsl={"type": "composite", "logic": logic, "conditions": conditions},
        priority=priority,
        domain=domain,
        tags=tags or frozenset(),
        persist=False,
    )


# GlobalRuleRepository


class TestGlobalRuleRepository:
    def test_add_and_get(self):
        repo = GlobalRuleRepository()
        r = _make_rule(1)
        repo.add_rule(r)
        assert repo.get(1) is r
        assert len(repo) == 1

    def test_add_rules_bulk(self):
        repo = GlobalRuleRepository()
        rules = [_make_rule(i) for i in range(10)]
        repo.add_rules(rules)
        assert len(repo) == 10

    def test_get_by_domain(self):
        repo = GlobalRuleRepository()
        repo.add_rules(
            [
                _make_rule(1, domain="fraud"),
                _make_rule(2, domain="fraud"),
                _make_rule(3, domain="loan"),
            ]
        )
        assert len(repo.get_by_domain("fraud")) == 2
        assert len(repo.get_by_domain("loan")) == 1
        assert len(repo.get_by_domain("missing")) == 0

    def test_get_by_tag(self):
        repo = GlobalRuleRepository()
        repo.add_rules(
            [
                _make_rule(1, tags=frozenset({"high_value"})),
                _make_rule(2, tags=frozenset({"high_value", "transaction"})),
                _make_rule(3, tags=frozenset({"low_value"})),
            ]
        )
        assert len(repo.get_by_tag("high_value")) == 2
        assert len(repo.get_by_tag("transaction")) == 1

    def test_remove(self):
        repo = GlobalRuleRepository()
        repo.add_rule(_make_rule(1, domain="fraud", tags=frozenset({"a"})))
        repo.remove(1)
        assert repo.get(1) is None
        assert len(repo) == 0

    def test_clear(self):
        repo = GlobalRuleRepository()
        repo.add_rules([_make_rule(i) for i in range(5)])
        repo.clear()
        assert len(repo) == 0

    def test_max_rules_limit(self):
        repo = GlobalRuleRepository(max_rules=3)
        repo.add_rules([_make_rule(i) for i in range(3)])
        with pytest.raises(ValueError, match="Repository full"):
            repo.add_rule(_make_rule(99))

    def test_get_all_domains(self):
        repo = GlobalRuleRepository()
        repo.add_rules(
            [
                _make_rule(1, domain="a"),
                _make_rule(2, domain="b"),
            ]
        )
        assert set(repo.get_all_domains()) == {"a", "b"}

    def test_get_nonexistent(self):
        repo = GlobalRuleRepository()
        assert repo.get(999) is None


# SegmentNetwork


class TestSegmentNetwork:
    def test_segment_creation_from_rule(self):
        net = SegmentNetwork()
        net.add_rules([_make_rule(1, field="amount")])
        assert len(net) >= 1

    def test_segment_sharing_across_domains(self):
        net = SegmentNetwork()
        net.add_rules(
            [
                _make_rule(1, field="amount", domain="fraud"),
                _make_rule(2, field="amount", domain="loan"),
            ]
        )
        # Both rules reference "amount", should share a segment
        assert len(net) == 1
        seg = list(net.segments.values())[0]
        assert {1, 2} == seg.rule_ids

    def test_separate_segments_different_fields(self):
        net = SegmentNetwork()
        net.add_rules(
            [
                _make_rule(1, field="amount"),
                _make_rule(2, field="country"),
            ]
        )
        assert len(net) == 2

    def test_affected_segments(self):
        net = SegmentNetwork()
        net.add_rules(
            [
                _make_rule(1, field="amount"),
                _make_rule(2, field="country"),
            ]
        )
        affected = net.get_affected_segments({"amount"})
        assert any(1 in s.rule_ids for s in affected)
        assert not any(2 in s.rule_ids for s in affected)

    def test_composite_rule_fields(self):
        net = SegmentNetwork()
        rule = _make_composite_rule(1, [("amount", ">", 100), ("country", "==", "US")])
        net.add_rules([rule])
        assert len(net) == 1
        seg = list(net.segments.values())[0]
        assert seg.fields == frozenset({"amount", "country"})

    def test_clear(self):
        net = SegmentNetwork()
        net.add_rules([_make_rule(1)])
        net.clear()
        assert len(net) == 0

    def test_get_segments_for_rule(self):
        net = SegmentNetwork()
        net.add_rules([_make_rule(1, field="amount")])
        segs = net.get_segments_for_rule(1)
        assert len(segs) == 1


# FieldIndex


class TestFieldIndex:
    def test_field_index_accuracy(self):
        idx = FieldIndex()
        idx.register("amount", "seg_1")
        idx.register("country", "seg_2")
        assert idx.get_affected_segments({"amount": 100}) == {"seg_1"}
        assert idx.get_affected_segments({"country": "US"}) == {"seg_2"}
        assert idx.get_affected_segments({"amount": 1, "country": "US"}) == {
            "seg_1",
            "seg_2",
        }

    def test_affected_segments_no_match(self):
        idx = FieldIndex()
        idx.register("amount", "seg_1")
        assert idx.get_affected_segments({"other": 1}) == set()

    def test_affected_rules(self):
        idx = FieldIndex()
        idx.register_rule("amount", 1)
        idx.register_rule("amount", 2)
        idx.register_rule("country", 3)
        assert idx.get_affected_rules({"amount": 100}) == {1, 2}

    def test_build_from_rules(self):
        idx = FieldIndex()
        rules = [_make_rule(1, field="amount"), _make_rule(2, field="country")]
        idx.build_from_rules(rules)
        assert len(idx) == 2

    def test_clear(self):
        idx = FieldIndex()
        idx.register("x", "s")
        idx.clear()
        assert len(idx) == 0


# UnifiedWorkingMemory


class TestUnifiedWorkingMemory:
    def test_assert_and_get(self):
        wm = UnifiedWorkingMemory()
        fid = wm.assert_fact({"amount": 100})
        assert wm.get_fact(fid) == {"amount": 100}
        assert len(wm) == 1

    def test_retract(self):
        wm = UnifiedWorkingMemory()
        fid = wm.assert_fact({"a": 1})
        assert wm.retract_fact(fid) is True
        assert len(wm) == 0

    def test_retract_nonexistent(self):
        wm = UnifiedWorkingMemory()
        assert wm.retract_fact("missing") is False

    def test_ttl_expiration(self):
        wm = UnifiedWorkingMemory(fact_ttl_ms=1)  # 1ms TTL
        wm.assert_fact({"a": 1})
        time.sleep(0.01)
        removed = wm.cleanup_expired_facts()
        assert removed == 1
        assert len(wm) == 0

    def test_get_all_facts(self):
        wm = UnifiedWorkingMemory()
        wm.assert_fact({"a": 1}, fact_id="f1")
        wm.assert_fact({"b": 2}, fact_id="f2")
        all_f = wm.get_all_facts()
        assert len(all_f) == 2

    def test_clear(self):
        wm = UnifiedWorkingMemory()
        wm.assert_fact({"a": 1})
        wm.clear()
        assert len(wm) == 0

    def test_custom_fact_id(self):
        wm = UnifiedWorkingMemory()
        fid = wm.assert_fact({"a": 1}, fact_id="my_id")
        assert fid == "my_id"
        assert wm.get_fact("my_id") == {"a": 1}


# TokenPropagator


class TestTokenPropagator:
    def test_propagate_single_segment(self):
        net = SegmentNetwork()
        wm = UnifiedWorkingMemory()
        net.add_rules([_make_rule(1, field="amount")])
        prop = TokenPropagator(net, wm)

        seg_ids = {s.segment_id for s in net.get_affected_segments({"amount"})}
        matched = prop.propagate({"amount": 500}, seg_ids)
        assert 1 in matched

    def test_propagate_no_match(self):
        net = SegmentNetwork()
        wm = UnifiedWorkingMemory()
        net.add_rules([_make_rule(1, field="amount")])
        prop = TokenPropagator(net, wm)

        seg_ids = {s.segment_id for s in net.get_affected_segments({"other"})}
        matched = prop.propagate({"other": 1}, seg_ids)
        assert matched == []

    def test_cross_domain_discovery(self):
        net = SegmentNetwork()
        wm = UnifiedWorkingMemory()
        r1 = _make_rule(1, field="amount", domain="fraud")
        r2 = _make_rule(2, field="amount", domain="loan")
        net.add_rules([r1, r2])
        prop = TokenPropagator(net, wm)

        seg_ids = {s.segment_id for s in net.get_affected_segments({"amount"})}
        matched = prop.propagate({"amount": 500}, seg_ids)
        assert set(matched) == {1, 2}

    def test_composite_requires_all_fields(self):
        net = SegmentNetwork()
        wm = UnifiedWorkingMemory()
        rule = _make_composite_rule(1, [("amount", ">", 100), ("country", "==", "US")])
        net.add_rules([rule])
        prop = TokenPropagator(net, wm)

        # Only amount → doesn't match (segment needs both fields)
        seg_ids = {s.segment_id for s in net.get_affected_segments({"amount"})}
        matched = prop.propagate({"amount": 500}, seg_ids)
        assert matched == []

        # Both fields → matches
        seg_ids = {s.segment_id for s in net.get_affected_segments({"amount", "country"})}
        matched = prop.propagate({"amount": 500, "country": "US"}, seg_ids)
        assert 1 in matched


# Agenda


class TestAgenda:
    def test_priority_ordering(self):
        agenda = Agenda()
        agenda.add_activation(rule_id=1, priority=1)
        agenda.add_activation(rule_id=2, priority=5)
        agenda.add_activation(rule_id=3, priority=3)

        act = agenda.next_activation()
        assert act.rule_id == 2  # highest priority first

    def test_empty(self):
        agenda = Agenda()
        assert agenda.is_empty()
        agenda.add_activation(rule_id=1, priority=0)
        assert not agenda.is_empty()

    def test_clear(self):
        agenda = Agenda()
        agenda.add_activation(rule_id=1, priority=0)
        agenda.clear()
        assert agenda.is_empty()

    def test_recency_same_priority(self):
        """With same priority, more recent activation fires first (Drools recency)."""
        agenda = Agenda()
        agenda.add_activation(rule_id=1, priority=5)
        agenda.add_activation(rule_id=2, priority=5)
        a1 = agenda.next_activation()
        a2 = agenda.next_activation()
        # Rule 2 was added later (more recent) → fires first
        assert a1.rule_id == 2
        assert a2.rule_id == 1


# EvaluationFilter


class TestEvaluationFilter:
    def test_frozen(self):
        f = EvaluationFilter(domains=frozenset({"fraud"}))
        assert f.domains == frozenset({"fraud"})

    def test_defaults(self):
        f = EvaluationFilter()
        assert f.domains is None
        assert f.tags is None
        assert f.min_priority is None
        assert f.max_priority is None


# _extract_fields utility


class TestExtractFields:
    def test_simple_condition(self):
        assert _extract_fields({"type": "condition", "field": "x"}) == {"x"}

    def test_composite(self):
        cond = {
            "type": "composite",
            "logic": "AND",
            "conditions": [
                {"type": "condition", "field": "a"},
                {"type": "condition", "field": "b"},
            ],
        }
        assert _extract_fields(cond) == {"a", "b"}

    def test_not(self):
        cond = {"type": "not", "condition": {"type": "condition", "field": "x"}}
        assert _extract_fields(cond) == {"x"}

    def test_exists(self):
        assert _extract_fields({"type": "exists", "field": "y"}) == {"y"}

    def test_empty(self):
        assert _extract_fields({}) == set()
        assert _extract_fields({"type": "unknown"}) == set()
