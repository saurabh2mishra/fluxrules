"""Tests that flat (non-hierarchical) evaluation preserves results (PHREAK P2.1).

The hierarchical-segment skip path was removed in P2.1 because it was inert (no
rule was ever mapped to a parent segment). These tests reproduce the original
result-correctness scenarios from the retired
``test_hierarchical_evaluation_optimization.py`` to prove that removing the dead
path changed no evaluation result, plus assert the engine exposes only the flat
path.
"""

import pytest

from fluxrules.engine.phreak._engine import PhreakEngine


def _and(rid, name, conds, priority=100, action=None):
    return {
        "id": rid,
        "name": name,
        "condition_dsl": {"type": "and", "conditions": conds},
        "action": action or f"log: {name}",
        "priority": priority,
    }


def _c(field, op, value):
    return {"type": "condition", "field": field, "op": op, "value": value}


class TestFlatEvaluationPreservesResults:
    """Removing the inert hierarchy path must not change any fired set."""

    def test_engine_has_no_hierarchy_state(self):
        """The engine exposes only the flat path (no hierarchy attributes)."""
        engine = PhreakEngine()
        engine.load_rules([_and(1, "r1", [_c("age", ">", 18)])])
        assert not hasattr(engine, "_has_hierarchical_segments")
        assert not hasattr(engine, "_rule_segments_cache")

    def test_shared_prefix_rules_fire_correctly(self):
        """Rules sharing a field prefix evaluate independently and correctly."""
        engine = PhreakEngine()
        rules = [
            _and(1, "parent", [_c("age", ">", 18), _c("status", "==", "active")]),
            _and(
                2,
                "child_score",
                [
                    _c("age", ">", 18),
                    _c("status", "==", "active"),
                    _c("score", ">", 100),
                ],
                priority=50,
            ),
            _and(
                3,
                "child_region",
                [
                    _c("age", ">", 18),
                    _c("status", "==", "active"),
                    _c("region", "==", "US"),
                ],
                priority=40,
            ),
        ]
        engine.load_rules(rules)

        # All conditions satisfied -> all three fire.
        result = engine.evaluate({"age": 25, "status": "active", "score": 150, "region": "US"})
        assert set(result.fired_rules) == {1, 2, 3}

        # Shared prefix fails -> none fire (no special skip needed; the AND fails).
        result = engine.evaluate({"age": 15, "status": "inactive", "score": 150, "region": "US"})
        assert set(result.fired_rules) == set()

    def test_partial_match_fires_only_satisfied_rules(self):
        engine = PhreakEngine()
        rules = [
            _and(1, "r1", [_c("a", ">", 10), _c("b", "<", 100)], priority=100),
            _and(
                2,
                "r2",
                [_c("a", ">", 10), _c("b", "<", 100), _c("c", "==", "x")],
                priority=90,
            ),
        ]
        engine.load_rules(rules)

        cases = [
            ({"a": 5, "b": 50, "c": "x"}, set()),
            ({"a": 15, "b": 50, "c": "x"}, {1, 2}),
            ({"a": 15, "b": 50, "c": "y"}, {1}),
            ({"a": 15, "b": 150, "c": "x"}, set()),
        ]
        for facts, expected in cases:
            result = engine.evaluate(facts)
            assert set(result.fired_rules) == expected, facts

    def test_streaming_mode_shared_prefix(self):
        engine = PhreakEngine(streaming_mode=True)
        rules = [
            _and(1, "r1", [_c("age", ">", 18), _c("status", "==", "active")]),
            _and(
                2,
                "r2",
                [
                    _c("age", ">", 18),
                    _c("status", "==", "active"),
                    _c("score", ">", 50),
                ],
                priority=90,
            ),
        ]
        engine.load_rules(rules)

        r1 = engine.evaluate({"age": 25, "status": "active", "score": 100})
        assert set(r1.fired_rules) == {1, 2}

        r2 = engine.evaluate({"age": 15, "status": "active", "score": 100})
        assert 1 not in r2.fired_rules
        assert 2 not in r2.fired_rules

        r3 = engine.evaluate({"age": 25, "status": "active", "score": 100})
        assert set(r3.fired_rules) == {1, 2}

    def test_independent_single_field_rules(self):
        engine = PhreakEngine()
        rules = [
            {
                "id": 1,
                "name": "r1",
                "condition_dsl": _c("age", ">", 18),
                "action": "log: r1",
                "priority": 100,
            },
            {
                "id": 2,
                "name": "r2",
                "condition_dsl": _c("status", "==", "active"),
                "action": "log: r2",
                "priority": 90,
            },
        ]
        engine.load_rules(rules)

        result = engine.evaluate({"age": 25, "status": "active"})
        assert set(result.fired_rules) == {1, 2}

        result = engine.evaluate({"age": 15, "status": "active"})
        assert set(result.fired_rules) == {2}


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
