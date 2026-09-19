"""Tests for dependency graph cycle detection."""

import pytest

from fluxrules.utils.dependency_graph_analyzer import (
    CyclicDependencyError,
    DependencyGraphAnalyzer,
)


class _MockRule:
    """Minimal rule-like object for testing."""

    def __init__(self, id: int, rule_dependencies=None):
        self.id = id
        self.rule_dependencies = rule_dependencies or set()


class TestDependencyGraphAnalyzer:
    """Tests for cycle detection and dependency analysis."""

    def test_no_cycles_independent_rules(self):
        rules = [_MockRule(1), _MockRule(2), _MockRule(3)]
        analyzer = DependencyGraphAnalyzer(rules)
        has_cycles, cycles = analyzer.has_cycles()
        assert not has_cycles
        assert cycles == []

    def test_simple_cycle_detected(self):
        rules = [
            _MockRule(1, rule_dependencies={2}),
            _MockRule(2, rule_dependencies={1}),
        ]
        analyzer = DependencyGraphAnalyzer(rules)
        has_cycles, cycles = analyzer.has_cycles()
        assert has_cycles
        assert len(cycles) > 0

    def test_complex_cycle_detected(self):
        rules = [
            _MockRule(1, rule_dependencies={2}),
            _MockRule(2, rule_dependencies={3}),
            _MockRule(3, rule_dependencies={1}),
        ]
        analyzer = DependencyGraphAnalyzer(rules)
        has_cycles, cycles = analyzer.has_cycles()
        assert has_cycles

    def test_no_cycle_linear_chain(self):
        rules = [
            _MockRule(1, rule_dependencies={2}),
            _MockRule(2, rule_dependencies={3}),
            _MockRule(3),
        ]
        analyzer = DependencyGraphAnalyzer(rules)
        has_cycles, cycles = analyzer.has_cycles()
        assert not has_cycles

    def test_depth_calculation(self):
        rules = [
            _MockRule(1, rule_dependencies={2}),
            _MockRule(2, rule_dependencies={3}),
            _MockRule(3),
        ]
        analyzer = DependencyGraphAnalyzer(rules)
        assert analyzer.get_depth(1) == 2
        assert analyzer.get_depth(3) == 0

    def test_topological_sort_no_cycles(self):
        rules = [
            _MockRule(1, rule_dependencies={2}),
            _MockRule(2, rule_dependencies={3}),
            _MockRule(3),
        ]
        analyzer = DependencyGraphAnalyzer(rules)
        order = analyzer.topological_sort()
        assert order.index(3) < order.index(2) < order.index(1)

    def test_topological_sort_raises_on_cycle(self):
        rules = [
            _MockRule(1, rule_dependencies={2}),
            _MockRule(2, rule_dependencies={1}),
        ]
        analyzer = DependencyGraphAnalyzer(rules)
        with pytest.raises(CyclicDependencyError, match="Circular rule dependencies"):
            analyzer.topological_sort()

    def test_empty_rules(self):
        analyzer = DependencyGraphAnalyzer([])
        has_cycles, cycles = analyzer.has_cycles()
        assert not has_cycles
        assert cycles == []

    def test_self_cycle(self):
        rules = [_MockRule(1, rule_dependencies={1})]
        analyzer = DependencyGraphAnalyzer(rules)
        has_cycles, cycles = analyzer.has_cycles()
        assert has_cycles
