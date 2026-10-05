"""Tests for PhreakEngine."""

from __future__ import annotations

import pytest

from fluxrules import Rule
from fluxrules.engine.infrastructure import EvaluationFilter
from fluxrules.engine.phreak import PhreakEngine


def _rule(
    rid: int,
    field: str = "amount",
    op: str = ">",
    value: int = 100,
    domain: str = "default",
    tags: frozenset[str] | None = None,
    priority: int = 0,
    action: str = "",
) -> Rule:
    return Rule(
        id=rid,
        name=f"rule_{rid}",
        condition_dsl={"type": "condition", "field": field, "op": op, "value": value},
        action=action,
        priority=priority,
        domain=domain,
        tags=tags or frozenset(),
        persist=False,
    )


def _composite_rule(
    rid: int,
    conditions: list[tuple[str, str, object]],
    logic: str = "AND",
    domain: str = "default",
    tags: frozenset[str] | None = None,
    priority: int = 0,
    action: str = "",
) -> Rule:
    return Rule(
        id=rid,
        name=f"rule_{rid}",
        condition_dsl={
            "type": "composite",
            "logic": logic,
            "conditions": [
                {"type": "condition", "field": f, "op": o, "value": v} for f, o, v in conditions
            ],
        },
        action=action,
        priority=priority,
        domain=domain,
        tags=tags or frozenset(),
        persist=False,
    )


# Parameterize over the engine to keep a single source of truth


@pytest.fixture(params=["phreak"])
def engine(request):
    return PhreakEngine()


class TestUnifiedEngineEvaluation:
    """Tests run against PhreakEngine."""

    def test_simple_match(self, engine):
        engine.load_rules([_rule(1, field="amount", op=">", value=100)])
        result = engine.evaluate({"amount": 200})
        assert 1 in result.fired_rules

    def test_simple_no_match(self, engine):
        engine.load_rules([_rule(1, field="amount", op=">", value=100)])
        result = engine.evaluate({"amount": 50})
        assert result.fired_rules == []

    def test_multi_rule_multi_domain(self, engine):
        engine.load_rules(
            [
                _rule(1, field="amount", op=">", value=100, domain="fraud"),
                _rule(2, field="amount", op=">", value=200, domain="loan"),
            ]
        )
        result = engine.evaluate({"amount": 500})
        assert set(result.fired_rules) == {1, 2}
        assert "fraud" in result.rules_by_domain
        assert "loan" in result.rules_by_domain

    def test_filter_by_domain(self, engine):
        engine.load_rules(
            [
                _rule(1, field="amount", op=">", value=100, domain="fraud"),
                _rule(2, field="amount", op=">", value=100, domain="loan"),
            ]
        )
        result = engine.evaluate_by_domain({"amount": 500}, domains=["fraud"])
        assert result.fired_rules == [1]

    def test_filter_by_tags(self, engine):
        engine.load_rules(
            [
                _rule(1, field="amount", op=">", value=100, tags=frozenset({"high_value"})),
                _rule(2, field="amount", op=">", value=100, tags=frozenset({"low_value"})),
            ]
        )
        result = engine.evaluate_by_tags({"amount": 500}, tags=["high_value"])
        assert result.fired_rules == [1]

    def test_combined_filter(self, engine):
        engine.load_rules(
            [
                _rule(
                    1,
                    field="amount",
                    op=">",
                    value=100,
                    domain="fraud",
                    tags=frozenset({"hv"}),
                    priority=5,
                ),
                _rule(
                    2,
                    field="amount",
                    op=">",
                    value=100,
                    domain="fraud",
                    tags=frozenset({"lv"}),
                    priority=1,
                ),
                _rule(
                    3,
                    field="amount",
                    op=">",
                    value=100,
                    domain="loan",
                    tags=frozenset({"hv"}),
                    priority=5,
                ),
            ]
        )
        f = EvaluationFilter(domains=frozenset({"fraud"}), tags=frozenset({"hv"}))
        result = engine.evaluate({"amount": 500}, filters=f)
        assert result.fired_rules == [1]

    def test_priority_ordering(self, engine):
        engine.load_rules(
            [
                _rule(1, field="amount", op=">", value=100, priority=1),
                _rule(2, field="amount", op=">", value=100, priority=10),
                _rule(3, field="amount", op=">", value=100, priority=5),
            ]
        )
        result = engine.evaluate({"amount": 500})
        assert result.fired_rules == [2, 3, 1]

    def test_composite_and(self, engine):
        engine.load_rules(
            [
                _composite_rule(1, [("amount", ">", 100), ("country", "==", "US")]),
            ]
        )
        assert engine.evaluate({"amount": 200, "country": "US"}).fired_rules == [1]
        assert engine.evaluate({"amount": 200, "country": "UK"}).fired_rules == []

    def test_composite_or(self, engine):
        engine.load_rules(
            [
                _composite_rule(1, [("amount", ">", 1000), ("country", "==", "US")], logic="OR"),
            ]
        )
        assert 1 in engine.evaluate({"amount": 2000, "country": "UK"}).fired_rules
        assert 1 in engine.evaluate({"amount": 50, "country": "US"}).fired_rules
        assert engine.evaluate({"amount": 50, "country": "UK"}).fired_rules == []

    def test_actions_collected(self, engine):
        engine.load_rules(
            [
                _rule(1, field="amount", op=">", value=100, action="flag_fraud"),
            ]
        )
        result = engine.evaluate({"amount": 500})
        assert "flag_fraud" in result.actions

    def test_explanations(self, engine):
        engine.load_rules([_rule(1, field="amount", op=">", value=100)])
        result = engine.evaluate({"amount": 500})
        assert 1 in result.explanations
        assert "rule_1" in result.explanations[1]

    def test_engine_type_in_result(self, engine):
        engine.load_rules([_rule(1)])
        result = engine.evaluate({"amount": 500})
        assert result.engine_type == "PhreakEngine"

    def test_latency_populated(self, engine):
        engine.load_rules([_rule(1)])
        result = engine.evaluate({"amount": 500})
        assert result.latency_ms >= 0

    def test_evaluate_all(self, engine):
        engine.load_rules([_rule(1, field="amount", op=">", value=100)])
        result = engine.evaluate_all({"amount": 500})
        assert 1 in result.fired_rules

    def test_no_rules_loaded(self, engine):
        result = engine.evaluate({"amount": 500})
        assert result.fired_rules == []

    def test_clear(self, engine):
        engine.load_rules([_rule(1)])
        engine.clear()
        result = engine.evaluate({"amount": 500})
        assert result.fired_rules == []

    def test_get_stats(self, engine):
        engine.load_rules([_rule(1), _rule(2, field="country", op="==", value="US")])
        stats = engine.get_stats()
        assert stats["rules_loaded"] == 2
        assert stats["segments_created"] >= 1

    def test_working_memory_lifecycle(self, engine):
        engine.load_rules([_rule(1)])
        fid = engine.assert_fact({"amount": 500})
        assert engine.working_memory.get_fact(fid) == {"amount": 500}
        engine.retract_fact(fid)
        assert engine.working_memory.get_fact(fid) is None

    def test_not_condition(self, engine):
        rule = Rule(
            id=1,
            name="not_rule",
            condition_dsl={
                "type": "not",
                "condition": {
                    "type": "condition",
                    "field": "blocked",
                    "op": "==",
                    "value": True,
                },
            },
            domain="test",
            persist=False,
        )
        engine.load_rules([rule])
        # blocked is True → NOT condition should be False → no match
        assert engine.evaluate({"blocked": True}).fired_rules == []
        # blocked is False → NOT condition should be True → match
        assert 1 in engine.evaluate({"blocked": False}).fired_rules

    def test_exists_condition(self, engine):
        rule = Rule(
            id=1,
            name="exists_rule",
            condition_dsl={"type": "exists", "field": "email"},
            domain="test",
            persist=False,
        )
        engine.load_rules([rule])
        assert 1 in engine.evaluate({"email": "a@b.com"}).fired_rules
        assert engine.evaluate({"name": "test"}).fired_rules == []

    def test_50_rules_multi_domain(self, engine):
        """Ensure 50 rules across 5 domains work correctly."""
        rules = []
        for i in range(50):
            domain = f"domain_{i % 5}"
            rules.append(_rule(i, field="amount", op=">", value=i * 10, domain=domain))
        engine.load_rules(rules)
        result = engine.evaluate({"amount": 1000})
        assert len(result.fired_rules) > 0
        assert len(result.rules_by_domain) > 0


class TestMinPriorityFilter:
    def test_min_priority(self):
        engine = PhreakEngine()
        engine.load_rules(
            [
                _rule(1, priority=1),
                _rule(2, priority=5),
                _rule(3, priority=10),
            ]
        )
        f = EvaluationFilter(min_priority=5)
        result = engine.evaluate({"amount": 500}, filters=f)
        assert set(result.fired_rules) == {2, 3}

    def test_max_priority(self):
        engine = PhreakEngine()
        engine.load_rules(
            [
                _rule(1, priority=1),
                _rule(2, priority=5),
                _rule(3, priority=10),
            ]
        )
        f = EvaluationFilter(max_priority=5)
        result = engine.evaluate({"amount": 500}, filters=f)
        assert set(result.fired_rules) == {1, 2}
