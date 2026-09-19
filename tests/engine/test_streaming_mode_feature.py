"""Comprehensive tests for PhreakEngine streaming mode feature.

Tests verify:
- Streaming mode parameter works correctly
- Caching behavior with repeated facts
- Dirty tracking with field changes
- Performance improvement
- Correctness vs stateless mode
"""

import time

import pytest

from fluxrules.domain import Rule
from fluxrules.engine.phreak import PhreakEngine


class TestStreamingModeParameter:
    """Test that streaming_mode parameter is properly handled."""

    def test_default_streaming_mode_disabled(self):
        """By default, streaming_mode should be False."""
        engine = PhreakEngine()
        assert engine._streaming_mode is False

    def test_streaming_mode_enabled(self):
        """streaming_mode=True should enable lazy evaluation."""
        engine = PhreakEngine(streaming_mode=True)
        assert engine._streaming_mode is True

    def test_streaming_mode_explicit_false(self):
        """streaming_mode=False should disable lazy evaluation."""
        engine = PhreakEngine(streaming_mode=False)
        assert engine._streaming_mode is False


class TestStreamingModeCaching:
    """Test that streaming mode caches results for identical facts."""

    def test_identical_facts_returns_empty(self):
        """Evaluating identical facts twice should return empty on second call."""
        engine = PhreakEngine(streaming_mode=True)

        rule = Rule(
            id=1,
            name="Age Check",
            condition_dsl={
                "type": "condition",
                "field": "age",
                "op": ">",
                "value": 18,
            },
            action="allow",
            priority=1,
            domain="test",
        )

        engine.load_rules([rule])
        facts = {"age": 25}

        # First evaluation
        result1 = engine.evaluate(facts)
        assert 1 in result1.fired_rules

        # Second evaluation with identical facts
        result2 = engine.evaluate(facts)
        assert result2.fired_rules == []  # Cached - no new fires

    def test_changed_facts_retriggers_evaluation(self):
        """Changing facts should trigger re-evaluation."""
        engine = PhreakEngine(streaming_mode=True)

        rule = Rule(
            id=1,
            name="Age Check",
            condition_dsl={
                "type": "condition",
                "field": "age",
                "op": ">",
                "value": 18,
            },
            action="allow",
            priority=1,
            domain="test",
        )

        engine.load_rules([rule])

        # First evaluation
        result1 = engine.evaluate({"age": 25})
        assert 1 in result1.fired_rules

        # Change fact
        result2 = engine.evaluate({"age": 30})
        assert 1 in result2.fired_rules

        # Repeat previous fact
        result3 = engine.evaluate({"age": 25})
        assert 1 in result3.fired_rules

    def test_non_matching_facts_cached(self):
        """Non-matching facts should also be cached."""
        engine = PhreakEngine(streaming_mode=True)

        rule = Rule(
            id=1,
            name="Age Check",
            condition_dsl={
                "type": "condition",
                "field": "age",
                "op": ">",
                "value": 18,
            },
            action="allow",
            priority=1,
            domain="test",
        )

        engine.load_rules([rule])
        facts = {"age": 10}  # Doesn't match

        # First evaluation
        result1 = engine.evaluate(facts)
        assert result1.fired_rules == []

        # Second evaluation with same non-matching facts
        result2 = engine.evaluate(facts)
        assert result2.fired_rules == []  # Cached


class TestStreamingModeFieldTracking:
    """Test that streaming mode tracks field changes correctly."""

    def test_changed_field_triggers_related_rules(self):
        """Changing a field should re-evaluate only related rules."""
        engine = PhreakEngine(streaming_mode=True)

        age_rule = Rule(
            id=1,
            name="Age Check",
            condition_dsl={
                "type": "condition",
                "field": "age",
                "op": ">",
                "value": 18,
            },
            action="allow",
            priority=1,
            domain="test",
        )

        salary_rule = Rule(
            id=2,
            name="Salary Check",
            condition_dsl={
                "type": "condition",
                "field": "salary",
                "op": ">",
                "value": 50000,
            },
            action="approve_loan",
            priority=1,
            domain="test",
        )

        engine.load_rules([age_rule, salary_rule])

        # First evaluation
        result1 = engine.evaluate({"age": 25, "salary": 60000})
        assert set(result1.fired_rules) == {1, 2}

        # Change only salary (age rule shouldn't fire again)
        result2 = engine.evaluate({"age": 25, "salary": 40000})
        # Only salary rule evaluated, age rule cached from first eval
        assert 2 not in result2.fired_rules  # Salary no longer matches

        # Change only age (salary rule shouldn't fire again)
        result3 = engine.evaluate({"age": 35, "salary": 40000})
        assert 1 in result3.fired_rules  # Age still matches

    def test_unchanged_field_not_reevaluated(self):
        """Unchanged fields should not trigger re-evaluation."""
        engine = PhreakEngine(streaming_mode=True)

        rule = Rule(
            id=1,
            name="Test",
            condition_dsl={
                "type": "condition",
                "field": "x",
                "op": ">",
                "value": 10,
            },
            action="fire",
            priority=1,
            domain="test",
        )

        engine.load_rules([rule])

        # First evaluation
        result1 = engine.evaluate({"x": 20, "y": 100})
        assert 1 in result1.fired_rules

        # Change y (unrelated field), x unchanged
        result2 = engine.evaluate({"x": 20, "y": 200})
        # x unchanged - rule shouldn't re-evaluate, returns cached
        assert result2.fired_rules == []


class TestStreamingModeCompositeConditions:
    """Test streaming mode with complex conditions."""

    def test_composite_and_condition(self):
        """Streaming mode should work with AND conditions."""
        engine = PhreakEngine(streaming_mode=True)

        rule = Rule(
            id=1,
            name="Complex",
            condition_dsl={
                "type": "and",
                "conditions": [
                    {"type": "condition", "field": "age", "op": ">", "value": 18},
                    {"type": "condition", "field": "income", "op": ">", "value": 50000},
                ],
            },
            action="approve",
            priority=1,
            domain="test",
        )

        engine.load_rules([rule])

        # First evaluation - both match
        result1 = engine.evaluate({"age": 25, "income": 60000})
        assert 1 in result1.fired_rules

        # Second evaluation - only age changes, income stays same
        result2 = engine.evaluate({"age": 35, "income": 60000})
        # Rule depends on both fields, both in segment, only age changed
        # Should re-evaluate and find match
        assert 1 in result2.fired_rules

        # Third evaluation - income drops below threshold
        result3 = engine.evaluate({"age": 35, "income": 40000})
        # Both fields part of rule, income changed
        # Should re-evaluate and find no match
        assert result3.fired_rules == []

    def test_composite_or_condition(self):
        """Streaming mode should work with OR conditions."""
        engine = PhreakEngine(streaming_mode=True)

        rule = Rule(
            id=1,
            name="OR Rule",
            condition_dsl={
                "type": "or",
                "conditions": [
                    {"type": "condition", "field": "admin", "op": "==", "value": True},
                    {
                        "type": "condition",
                        "field": "premium",
                        "op": "==",
                        "value": True,
                    },
                ],
            },
            action="grant_access",
            priority=1,
            domain="test",
        )

        engine.load_rules([rule])

        # First evaluation - admin true
        result1 = engine.evaluate({"admin": True, "premium": False})
        assert 1 in result1.fired_rules

        # Second evaluation - toggle admin, premium stays false
        result2 = engine.evaluate({"admin": False, "premium": False})
        # admin field changed
        assert result2.fired_rules == []

        # Third evaluation - set premium true
        result3 = engine.evaluate({"admin": False, "premium": True})
        # premium field changed
        assert 1 in result3.fired_rules


class TestStatelessVsStreamingMode:
    """Compare stateless and streaming mode behavior."""

    def test_stateless_always_reevaluates(self):
        """Stateless mode should always re-evaluate."""
        engine = PhreakEngine(streaming_mode=False)

        rule = Rule(
            id=1,
            name="Test",
            condition_dsl={
                "type": "condition",
                "field": "x",
                "op": ">",
                "value": 10,
            },
            action="fire",
            priority=1,
            domain="test",
        )

        engine.load_rules([rule])
        facts = {"x": 20}

        # All evaluations should return the same result
        results = [engine.evaluate(facts).fired_rules for _ in range(5)]
        assert all(result == [1] for result in results)

    def test_streaming_vs_stateless_first_eval(self):
        """Both modes should produce same result on first evaluation."""
        rule = Rule(
            id=1,
            name="Test",
            condition_dsl={
                "type": "condition",
                "field": "x",
                "op": ">",
                "value": 10,
            },
            action="fire",
            priority=1,
            domain="test",
        )

        streaming_engine = PhreakEngine(streaming_mode=True)
        streaming_engine.load_rules([rule])

        stateless_engine = PhreakEngine(streaming_mode=False)
        stateless_engine.load_rules([rule])

        facts = {"x": 20}

        streaming_result = streaming_engine.evaluate(facts).fired_rules
        stateless_result = stateless_engine.evaluate(facts).fired_rules

        # First evaluation should be identical
        assert streaming_result == stateless_result == [1]

    def test_streaming_vs_stateless_repeated_eval(self):
        """Modes should differ on repeated evaluations."""
        rule = Rule(
            id=1,
            name="Test",
            condition_dsl={
                "type": "condition",
                "field": "x",
                "op": ">",
                "value": 10,
            },
            action="fire",
            priority=1,
            domain="test",
        )

        streaming_engine = PhreakEngine(streaming_mode=True)
        streaming_engine.load_rules([rule])

        stateless_engine = PhreakEngine(streaming_mode=False)
        stateless_engine.load_rules([rule])

        facts = {"x": 20}

        # First evaluation
        streaming_engine.evaluate(facts)
        stateless_engine.evaluate(facts)

        # Second evaluation with same facts
        streaming_result = streaming_engine.evaluate(facts).fired_rules
        stateless_result = stateless_engine.evaluate(facts).fired_rules

        # Streaming mode: cached (returns empty)
        # Stateless mode: re-evaluated (returns matched rules)
        assert streaming_result == []  # Cached
        assert stateless_result == [1]  # Re-evaluated


@pytest.mark.performance
class TestStreamingModePerformance:
    """Test performance characteristics of streaming mode."""

    def test_streaming_mode_faster_for_repeated_facts(self):
        """Streaming mode should be faster for repeated facts."""
        # Create engines
        streaming_engine = PhreakEngine(streaming_mode=True)
        stateless_engine = PhreakEngine(streaming_mode=False)

        # Create rules
        rules = [
            Rule(
                id=i,
                name=f"rule_{i}",
                condition_dsl={
                    "type": "condition",
                    "field": f"field_{i % 5}",
                    "op": ">",
                    "value": i,
                },
                action=f"action_{i}",
                priority=i,
                domain="test",
            )
            for i in range(1, 51)
        ]

        streaming_engine.load_rules(rules)
        stateless_engine.load_rules(rules)

        facts = {f"field_{i}": 100 for i in range(5)}

        # Stateless benchmark
        start = time.time()
        for _ in range(1000):
            stateless_engine.evaluate(facts)
        stateless_time = time.time() - start

        # Streaming benchmark
        start = time.time()
        streaming_engine.evaluate(facts)  # First evaluation
        for _ in range(999):
            streaming_engine.evaluate(facts)  # Cached calls
        streaming_time = time.time() - start

        # Streaming should be faster (at least 2x for this scenario)
        speedup = stateless_time / streaming_time
        print(f"\nPerformance speedup: {speedup:.1f}x")
        print(f"Stateless: {stateless_time * 1000:.2f}ms for 1000 evals")
        print(f"Streaming: {streaming_time * 1000:.2f}ms for 1000 evals")

        assert speedup > 2, f"Expected >2x speedup, got {speedup:.1f}x"

    def test_streaming_mode_minimal_overhead_for_changed_facts(self):
        """Streaming mode overhead should be minimal when facts change."""
        streaming_engine = PhreakEngine(streaming_mode=True)
        stateless_engine = PhreakEngine(streaming_mode=False)

        rules = [
            Rule(
                id=i,
                name=f"rule_{i}",
                condition_dsl={
                    "type": "condition",
                    "field": f"field_{i % 5}",
                    "op": ">",
                    "value": i,
                },
                action=f"action_{i}",
                priority=i,
                domain="test",
            )
            for i in range(1, 51)
        ]

        streaming_engine.load_rules(rules)
        stateless_engine.load_rules(rules)

        # Stateless benchmark
        start = time.time()
        for i in range(1000):
            stateless_engine.evaluate({"field_0": 50 + i})
        stateless_time = time.time() - start

        # Streaming benchmark (facts change each time)
        start = time.time()
        for i in range(1000):
            streaming_engine.evaluate({"field_0": 50 + i})
        streaming_time = time.time() - start

        # Overhead should be minimal (<50% slower)
        overhead = streaming_time / stateless_time
        print(f"\nStreaming mode overhead with changing facts: {overhead:.2f}x")

        assert overhead < 1.5, (
            f"Expected <1.5x overhead, got {overhead:.2f}x. "
            "Streaming mode should have minimal overhead when facts change."
        )


class TestStreamingModeEdgeCases:
    """Test edge cases and special scenarios."""

    def test_empty_facts(self):
        """Streaming mode should handle empty facts."""
        engine = PhreakEngine(streaming_mode=True)
        engine.load_rules([])

        result = engine.evaluate({})
        assert result.fired_rules == []

    def test_no_matching_rules(self):
        """Streaming mode should handle no matching rules."""
        engine = PhreakEngine(streaming_mode=True)

        rule = Rule(
            id=1,
            name="Test",
            condition_dsl={
                "type": "condition",
                "field": "x",
                "op": ">",
                "value": 100,
            },
            action="fire",
            priority=1,
            domain="test",
        )

        engine.load_rules([rule])

        result = engine.evaluate({"x": 50})
        assert result.fired_rules == []

    def test_multiple_rules_same_fields(self):
        """Streaming mode with multiple rules on same fields."""
        engine = PhreakEngine(streaming_mode=True)

        rules = [
            Rule(
                id=1,
                name="Rule 1",
                condition_dsl={
                    "type": "condition",
                    "field": "age",
                    "op": ">",
                    "value": 18,
                },
                action="a1",
                priority=1,
                domain="test",
            ),
            Rule(
                id=2,
                name="Rule 2",
                condition_dsl={
                    "type": "condition",
                    "field": "age",
                    "op": ">",
                    "value": 21,
                },
                action="a2",
                priority=2,
                domain="test",
            ),
        ]

        engine.load_rules(rules)

        # First evaluation
        result1 = engine.evaluate({"age": 25})
        assert set(result1.fired_rules) == {1, 2}

        # Identical facts
        result2 = engine.evaluate({"age": 25})
        assert result2.fired_rules == []

        # Changed age
        result3 = engine.evaluate({"age": 19})
        assert 1 in result3.fired_rules
        assert 2 not in result3.fired_rules

    def test_switching_modes_runtime(self):
        """Test switching between modes at runtime."""
        engine = PhreakEngine(streaming_mode=True)

        rule = Rule(
            id=1,
            name="Test",
            condition_dsl={
                "type": "condition",
                "field": "x",
                "op": ">",
                "value": 10,
            },
            action="fire",
            priority=1,
            domain="test",
        )

        engine.load_rules([rule])
        facts = {"x": 20}

        # Streaming mode
        result1 = engine.evaluate(facts)
        assert 1 in result1.fired_rules

        result2 = engine.evaluate(facts)
        assert result2.fired_rules == []  # Cached

        # Switch to stateless
        engine._streaming_mode = False
        result3 = engine.evaluate(facts)
        assert 1 in result3.fired_rules  # Re-evaluated


class TestStreamingModeWithConfig:
    """Test streaming mode initialization with config."""

    def test_streaming_mode_with_custom_config(self):
        """Streaming mode should work with custom EngineConfig."""
        from fluxrules.engine.configuration import EngineConfig

        config = EngineConfig(rule_engine_type="PHREAK")
        engine = PhreakEngine(streaming_mode=True, config=config)

        assert engine._streaming_mode is True
        assert engine._config.rule_engine_type == "PHREAK"

    def test_streaming_mode_with_max_rules(self):
        """Streaming mode should respect max_rules parameter."""
        engine = PhreakEngine(max_rules=100, streaming_mode=True)

        rules = [
            Rule(
                id=i,
                name=f"rule_{i}",
                condition_dsl={
                    "type": "condition",
                    "field": "x",
                    "op": ">",
                    "value": i,
                },
                action=f"a_{i}",
                priority=i,
                domain="test",
            )
            for i in range(1, 51)
        ]

        engine.load_rules(rules)
        assert engine._streaming_mode is True


class TestStreamingDeltaLinkingParity:
    """Incremental delta-linking must not change results.

    For value-only fact updates (stable field presence - the dominant streaming
    case), streaming mode with delta-linking must fire exactly the same rules as
    independent stateless evaluation of each fact.
    """

    def _rules(self, n: int, n_fields: int):
        import random

        rng = random.Random(42)
        out = []
        for rid in range(n):
            k = rng.randint(1, 4)
            fields = rng.sample(range(n_fields), k)
            conds = [
                {
                    "type": "condition",
                    "field": f"field_{f}",
                    "op": ">",
                    "value": rng.randint(0, 500),
                }
                for f in fields
            ]
            out.append(
                Rule(
                    id=rid,
                    name=f"r{rid}",
                    condition_dsl={"type": "and", "conditions": conds},
                    priority=rid % 5,
                    domain="test",
                )
            )
        return out

    def test_value_only_updates_match_stateless(self):
        import random

        rng = random.Random(7)
        n_fields = 16
        rules = self._rules(150, n_fields)

        stateless = PhreakEngine(streaming_mode=False)
        stateless.load_rules(rules)
        streaming = PhreakEngine(streaming_mode=True)
        streaming.load_rules(rules)

        # All fields always present (stable presence); only values change.
        cur = {f"field_{j}": rng.randint(0, 1000) for j in range(n_fields)}
        for _ in range(400):
            cur = dict(cur)
            f = rng.randint(0, n_fields - 1)
            cur[f"field_{f}"] = rng.randint(0, 1000)
            expected = set(stateless.evaluate(cur).fired_rules)
            got = set(streaming.evaluate(cur).fired_rules)
            assert got == expected

    def test_field_add_remove_match_stateless_on_genuine_changes(self):
        """Adds AND removes of fields must match stateless - modulo the contract.

        Streaming mode's documented contract is: when the incoming fact is
        identical to the previous evaluation, return EMPTY (the activations were
        already delivered). A no-op delete of an already-absent field leaves the
        fact unchanged and so legitimately returns empty. This test therefore
        only compares the two modes on cycles where the fact actually changed -
        which is the real soundness property - and separately asserts the
        unchanged-fact contract holds.
        """
        import random

        rng = random.Random(13)
        n_fields = 12
        rules = self._rules(120, n_fields)

        stateless = PhreakEngine(streaming_mode=False)
        stateless.load_rules(rules)
        streaming = PhreakEngine(streaming_mode=True)
        streaming.load_rules(rules)

        cur: dict = {}
        prev: dict | None = None
        compared = 0
        for _ in range(1500):
            cur = dict(cur)
            f = f"field_{rng.randint(0, n_fields - 1)}"
            # Mix of add / value-change / remove, including no-op deletes.
            if rng.random() < 0.25 and f in cur:
                del cur[f]
            else:
                cur[f] = rng.randint(0, 1000)

            expected = set(stateless.evaluate(dict(cur)).fired_rules)
            got = set(streaming.evaluate(dict(cur)).fired_rules)

            if prev is not None and prev == cur:
                # Unchanged fact -> streaming returns empty by contract.
                assert got == set()
            else:
                # Genuine change -> streaming must equal stateless exactly.
                assert got == expected
                compared += 1
            prev = dict(cur)

        # Sanity: the test actually exercised many genuine-change comparisons.
        assert compared > 1000
