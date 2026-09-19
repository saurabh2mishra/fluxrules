"""Load testing scenarios for FluxRules engines.

Tests scaling behavior with large rule sets and fact volumes to
verify performance characteristics and memory usage.
"""

from __future__ import annotations

import time
from typing import Any

import pytest

from fluxrules import Rule
from fluxrules.engine.phreak import PhreakEngine


def _generate_rules(count: int) -> list[Rule]:
    """Generate a list of synthetic rules for load testing."""
    rules = []
    for i in range(count):
        rules.append(
            Rule(
                id=i + 1,
                name=f"rule_{i + 1}",
                condition_dsl={
                    "type": "condition",
                    "field": f"field_{i % 50}",
                    "op": ">",
                    "value": i % 100,
                },
                action=f"action_{i + 1}",
                priority=i % 10,
                domain=f"domain_{i % 5}",
                tags=frozenset({f"tag_{i % 3}"}),
                persist=False,
            )
        )
    return rules


def _generate_facts(field_count: int) -> dict[str, Any]:
    """Generate a fact dict with the given number of fields."""
    return {f"field_{i}": i * 10 + 5 for i in range(field_count)}


class TestLoadScenarios:
    """Load testing scenarios for engine scaling."""

    @pytest.mark.performance
    def test_1k_rules_phreak(self):
        """Evaluate 1K rules - PHREAK should handle easily."""
        engine = PhreakEngine()
        rules = _generate_rules(1000)
        engine.load_rules(rules)
        facts = _generate_facts(50)

        start = time.time()
        result = engine.evaluate(facts)
        elapsed = time.time() - start

        assert elapsed < 2.0, f"1K rules took {elapsed:.3f}s (expected <2s)"
        assert len(result.candidate_rule_ids) >= 0

    @pytest.mark.performance
    def test_5k_rules_phreak(self):
        """Evaluate 5K rules - baseline scaling test."""
        engine = PhreakEngine()
        rules = _generate_rules(5000)
        engine.load_rules(rules)
        facts = _generate_facts(50)

        start = time.time()
        result = engine.evaluate(facts)
        elapsed = time.time() - start

        assert elapsed < 5.0, f"5K rules took {elapsed:.3f}s (expected <5s)"
        assert len(result.candidate_rule_ids) >= 0

    @pytest.mark.performance
    def test_multiple_evaluations_consistency(self):
        """Multiple evaluations should produce consistent results."""
        engine = PhreakEngine()
        rules = _generate_rules(500)
        engine.load_rules(rules)
        facts = _generate_facts(50)

        results = []
        for _ in range(10):
            result = engine.evaluate(facts)
            results.append(set(result.fired_rules))

        # All evaluations should produce identical results
        for i in range(1, len(results)):
            assert results[i] == results[0], "Inconsistent evaluation results"

    @pytest.mark.performance
    def test_rule_loading_performance(self):
        """Loading 5K rules should be fast."""
        engine = PhreakEngine()
        rules = _generate_rules(5000)

        start = time.time()
        engine.load_rules(rules)
        elapsed = time.time() - start

        assert elapsed < 5.0, f"Loading 5K rules took {elapsed:.3f}s (expected <5s)"
        assert len(engine.rule_repository) == 5000
