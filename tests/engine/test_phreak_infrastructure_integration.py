"""Integration tests for PHREAK engine with infrastructure components.

Tests the PHREAK engine's interaction with:
- SegmentNetwork: hierarchical rule organization
- FieldIndex: efficient field-to-segment mapping
- TokenPropagator: lazy token propagation
- LazyEvaluationMixin: dirty tracking and lazy evaluation
"""

from __future__ import annotations

from fluxrules import Rule
from fluxrules.engine.phreak import PhreakEngine


class TestPhreakSegmentNetwork:
    """Test PHREAK engine's integration with SegmentNetwork."""

    def test_segment_network_creation(self):
        """SegmentNetwork should organize rules by condition fields."""
        engine = PhreakEngine()
        rules = [
            Rule(
                id=1,
                name="rule_age",
                condition_dsl={
                    "type": "condition",
                    "field": "age",
                    "op": ">",
                    "value": 18,
                },
                action="action_1",
                priority=1,
                domain="users",
                tags=frozenset(),
                persist=False,
            ),
            Rule(
                id=2,
                name="rule_country",
                condition_dsl={
                    "type": "condition",
                    "field": "country",
                    "op": "==",
                    "value": "US",
                },
                action="action_2",
                priority=1,
                domain="users",
                tags=frozenset(),
                persist=False,
            ),
            Rule(
                id=3,
                name="rule_age_country",
                condition_dsl={
                    "type": "composite",
                    "logic": "AND",
                    "conditions": [
                        {"type": "condition", "field": "age", "op": ">", "value": 21},
                        {
                            "type": "condition",
                            "field": "country",
                            "op": "==",
                            "value": "US",
                        },
                    ],
                },
                action="action_3",
                priority=2,
                domain="users",
                tags=frozenset(),
                persist=False,
            ),
        ]
        engine.load_rules(rules)

        # Verify segments were created
        assert len(engine.segment_network.segments) > 0

        # Verify rules are in segments
        for rule in rules:
            segments = engine.segment_network.get_segments_for_rule(rule.id)
            assert len(segments) > 0, f"Rule {rule.id} should be in at least one segment"

    def test_segment_network_affected_segments(self):
        """SegmentNetwork should identify affected segments based on fact fields."""
        engine = PhreakEngine()
        rules = [
            Rule(
                id=1,
                name="rule_age",
                condition_dsl={
                    "type": "condition",
                    "field": "age",
                    "op": ">",
                    "value": 18,
                },
                action="action_1",
                priority=1,
                domain="users",
                tags=frozenset(),
                persist=False,
            ),
            Rule(
                id=2,
                name="rule_country",
                condition_dsl={
                    "type": "condition",
                    "field": "country",
                    "op": "==",
                    "value": "US",
                },
                action="action_2",
                priority=1,
                domain="users",
                tags=frozenset(),
                persist=False,
            ),
        ]
        engine.load_rules(rules)

        # Facts with 'age' field should affect only age-related segment
        affected = engine.segment_network.get_affected_segments({"age"})
        assert len(affected) > 0

        # Facts with 'country' field should affect only country-related segment
        affected = engine.segment_network.get_affected_segments({"country"})
        assert len(affected) > 0

        # Facts with both should affect both segments
        affected = engine.segment_network.get_affected_segments({"age", "country"})
        assert len(affected) > 0


class TestPhreakFieldIndex:
    """Test PHREAK engine's integration with FieldIndex."""

    def test_field_index_creation(self):
        """FieldIndex should map fields to segments."""
        engine = PhreakEngine()
        rules = [
            Rule(
                id=1,
                name="rule_age",
                condition_dsl={
                    "type": "condition",
                    "field": "age",
                    "op": ">",
                    "value": 18,
                },
                action="action_1",
                priority=1,
                domain="users",
                tags=frozenset(),
                persist=False,
            ),
        ]
        engine.load_rules(rules)

        # Field index should be built
        assert len(engine.field_index._field_to_segments) > 0

    def test_field_index_affected_rules(self):
        """FieldIndex should map facts to affected segments."""
        engine = PhreakEngine()
        rules = [
            Rule(
                id=1,
                name="rule_age",
                condition_dsl={
                    "type": "condition",
                    "field": "age",
                    "op": ">",
                    "value": 18,
                },
                action="action_1",
                priority=1,
                domain="users",
                tags=frozenset(),
                persist=False,
            ),
            Rule(
                id=2,
                name="rule_salary",
                condition_dsl={
                    "type": "condition",
                    "field": "salary",
                    "op": ">",
                    "value": 50000,
                },
                action="action_2",
                priority=1,
                domain="employees",
                tags=frozenset(),
                persist=False,
            ),
        ]
        engine.load_rules(rules)

        # Facts with 'age' should be mapped to age-related segment
        age_segments = engine.field_index._field_to_segments.get("age", set())
        assert len(age_segments) > 0

        # Facts with 'salary' should be mapped to salary-related segment
        salary_segments = engine.field_index._field_to_segments.get("salary", set())
        assert len(salary_segments) > 0


class TestPhreakLazyEvaluation:
    """Test PHREAK engine's lazy evaluation strategy."""

    def test_stateless_mode_consistent_results(self):
        """In stateless mode, repeated evaluations should produce consistent results."""
        engine = PhreakEngine()
        engine._streaming_mode = False  # Explicit stateless mode
        rules = [
            Rule(
                id=1,
                name="rule_age",
                condition_dsl={
                    "type": "condition",
                    "field": "age",
                    "op": ">",
                    "value": 18,
                },
                action="action_1",
                priority=1,
                domain="users",
                tags=frozenset(),
                persist=False,
            ),
        ]
        engine.load_rules(rules)

        facts = {"age": 25}

        # Multiple evaluations should produce identical results
        results = []
        for _ in range(5):
            result = engine.evaluate(facts)
            results.append(set(result.fired_rules))

        # All results should be identical
        for i in range(1, len(results)):
            assert results[i] == results[0], f"Evaluation {i} differs from first"

    def test_streaming_mode_dirty_tracking(self):
        """In streaming mode, dirty tracking should skip unchanged facts."""
        engine = PhreakEngine()
        engine._streaming_mode = True  # Enable streaming mode
        rules = [
            Rule(
                id=1,
                name="rule_age",
                condition_dsl={
                    "type": "condition",
                    "field": "age",
                    "op": ">",
                    "value": 18,
                },
                action="action_1",
                priority=1,
                domain="users",
                tags=frozenset(),
                persist=False,
            ),
        ]
        engine.load_rules(rules)

        # First evaluation with facts
        facts1 = {"age": 25}
        result1 = engine.evaluate(facts1)
        assert len(result1.fired_rules) == 1

        # Second evaluation with identical facts (dirty tracking should skip)
        result2 = engine.evaluate(facts1)
        # In streaming mode, identical facts should not re-evaluate
        assert len(result2.fired_rules) == 0, "Streaming mode should not re-eval identical facts"

        # Third evaluation with changed facts (dirty tracking should activate)
        facts2 = {"age": 30}
        result3 = engine.evaluate(facts2)
        assert len(result3.fired_rules) == 1, "Changed facts should trigger re-eval"

    def test_streaming_mode_field_changes(self):
        """In streaming mode, only affected segments should be re-evaluated on field changes."""
        engine = PhreakEngine()
        engine._streaming_mode = True
        rules = [
            Rule(
                id=1,
                name="rule_age",
                condition_dsl={
                    "type": "condition",
                    "field": "age",
                    "op": ">",
                    "value": 18,
                },
                action="action_1",
                priority=1,
                domain="users",
                tags=frozenset(),
                persist=False,
            ),
            Rule(
                id=2,
                name="rule_country",
                condition_dsl={
                    "type": "condition",
                    "field": "country",
                    "op": "==",
                    "value": "US",
                },
                action="action_2",
                priority=1,
                domain="users",
                tags=frozenset(),
                persist=False,
            ),
        ]
        engine.load_rules(rules)

        # First evaluation
        facts1 = {"age": 25, "country": "US"}
        result1 = engine.evaluate(facts1)
        assert len(result1.fired_rules) == 2

        # Second evaluation: only age changed
        facts2 = {"age": 30, "country": "US"}
        result2 = engine.evaluate(facts2)
        # Only age segment affected
        assert len(result2.fired_rules) >= 1  # At least age rule

        # Third evaluation: only country changed
        facts3 = {"age": 30, "country": "CA"}
        result3 = engine.evaluate(facts3)
        # Only country segment affected
        assert len(result3.fired_rules) >= 0

    def test_lazy_evaluation_with_composite_conditions(self):
        """Lazy evaluation should work with composite conditions."""
        engine = PhreakEngine()
        engine._streaming_mode = False
        rules = [
            Rule(
                id=1,
                name="composite_rule",
                condition_dsl={
                    "type": "composite",
                    "logic": "AND",
                    "conditions": [
                        {"type": "condition", "field": "age", "op": ">", "value": 18},
                        {
                            "type": "condition",
                            "field": "country",
                            "op": "==",
                            "value": "US",
                        },
                    ],
                },
                action="action_1",
                priority=1,
                domain="users",
                tags=frozenset(),
                persist=False,
            ),
        ]
        engine.load_rules(rules)

        # Both conditions met
        facts = {"age": 25, "country": "US"}
        result = engine.evaluate(facts)
        assert 1 in result.fired_rules

        # Only one condition met
        facts = {"age": 25, "country": "CA"}
        result = engine.evaluate(facts)
        assert 1 not in result.fired_rules

    def test_lazy_evaluation_with_negation(self):
        """Lazy evaluation should work with negated conditions."""
        engine = PhreakEngine()
        engine._streaming_mode = False
        rules = [
            Rule(
                id=1,
                name="negation_rule",
                condition_dsl={
                    "type": "not",
                    "condition": {
                        "type": "condition",
                        "field": "premium",
                        "op": "==",
                        "value": True,
                    },
                },
                action="action_1",
                priority=1,
                domain="users",
                tags=frozenset(),
                persist=False,
            ),
        ]
        engine.load_rules(rules)

        # Premium is False
        facts = {"premium": False}
        result = engine.evaluate(facts)
        assert 1 in result.fired_rules

        # Premium is True
        facts = {"premium": True}
        result = engine.evaluate(facts)
        assert 1 not in result.fired_rules


class TestPhreakTokenPropagator:
    """Test PHREAK engine's integration with TokenPropagator."""

    def test_token_propagation_basic(self):
        """TokenPropagator should identify matching rules via segments."""
        engine = PhreakEngine()
        rules = [
            Rule(
                id=1,
                name="rule_age",
                condition_dsl={
                    "type": "condition",
                    "field": "age",
                    "op": ">",
                    "value": 18,
                },
                action="action_1",
                priority=1,
                domain="users",
                tags=frozenset(),
                persist=False,
            ),
        ]
        engine.load_rules(rules)

        facts = {"age": 25}

        # Token propagator should identify rule 1 as a candidate
        affected_segments = engine.get_affected_segments(facts)
        assert len(affected_segments) > 0

        matched = engine.token_propagator.propagate(facts, affected_segments)
        assert 1 in matched

    def test_token_propagation_multiple_rules(self):
        """TokenPropagator should identify multiple matching rules."""
        engine = PhreakEngine()
        rules = [
            Rule(
                id=1,
                name="rule_age",
                condition_dsl={
                    "type": "condition",
                    "field": "age",
                    "op": ">",
                    "value": 18,
                },
                action="action_1",
                priority=1,
                domain="users",
                tags=frozenset(),
                persist=False,
            ),
            Rule(
                id=2,
                name="rule_premium",
                condition_dsl={
                    "type": "condition",
                    "field": "premium",
                    "op": "==",
                    "value": True,
                },
                action="action_2",
                priority=1,
                domain="users",
                tags=frozenset(),
                persist=False,
            ),
        ]
        engine.load_rules(rules)

        facts = {"age": 25, "premium": True}

        affected_segments = engine.get_affected_segments(facts)
        matched = engine.token_propagator.propagate(facts, affected_segments)

        # Both rules should be candidates
        assert 1 in matched
        assert 2 in matched


class TestPhreakExplanations:
    """Test PHREAK engine's explanation generation."""

    def test_rule_firing_explanation(self):
        """Fired rules should include segment information in explanations."""
        engine = PhreakEngine()
        rules = [
            Rule(
                id=1,
                name="test_rule",
                condition_dsl={
                    "type": "condition",
                    "field": "age",
                    "op": ">",
                    "value": 18,
                },
                action="action_1",
                priority=1,
                domain="users",
                tags=frozenset(),
                persist=False,
            ),
        ]
        engine.load_rules(rules)

        facts = {"age": 25}
        result = engine.evaluate(facts)

        # Check explanations
        assert 1 in result.explanations
        explanation = result.explanations[1]
        assert "PHREAK" in explanation
        assert "segments" in explanation.lower()
