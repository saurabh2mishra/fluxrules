"""Dependency graph cycle detection for rules.

Detects circular dependencies among rules that reference each other,
preventing infinite loops or resource exhaustion at load time.
"""

from __future__ import annotations

from fluxrules.domain.errors import FluxRulesError


class CyclicDependencyError(FluxRulesError):
    """Raised when circular rule dependencies are detected."""

    code = "CYCLIC_DEPENDENCY"


class DependencyGraphAnalyzer:
    """Analyze rule dependencies for cycles and depth.

    Works with any iterable of rule-like objects that have an ``id``
    attribute and an optional ``rule_dependencies`` attribute (a set
    or list of rule IDs this rule depends on).
    """

    def __init__(self, rules) -> None:
        self.graph: dict[int, set[int]] = {}
        self._build_graph(rules)

    def _build_graph(self, rules) -> None:
        """Build adjacency list from rules."""
        for rule in rules:
            rid = rule.id
            deps: set[int] = set()
            if hasattr(rule, "rule_dependencies") and rule.rule_dependencies:
                deps = set(rule.rule_dependencies)
            self.graph[rid] = deps

    def has_cycles(self) -> tuple[bool, list[list[int]]]:
        """Detect cycles using DFS.

        Returns:
            (has_cycles, list_of_cycles) where each cycle is a list of rule IDs.
        """
        visited: set[int] = set()
        rec_stack: set[int] = set()
        cycles: list[list[int]] = []

        def dfs(node: int, path: list[int]) -> None:
            visited.add(node)
            rec_stack.add(node)
            path.append(node)

            for neighbor in self.graph.get(node, set()):
                if neighbor not in visited:
                    dfs(neighbor, path)
                elif neighbor in rec_stack:
                    cycle_start = path.index(neighbor)
                    cycles.append(path[cycle_start:] + [neighbor])

            path.pop()
            rec_stack.remove(node)

        for rule_id in self.graph:
            if rule_id not in visited:
                dfs(rule_id, [])

        return len(cycles) > 0, cycles

    def get_depth(self, rule_id: int, max_depth: int = 10) -> int:
        """Get maximum dependency depth for a rule."""
        if rule_id not in self.graph:
            return 0

        visited: set[int] = {rule_id}

        def _dfs(node: int, depth: int) -> int:
            if depth > max_depth:
                return depth
            max_d = depth
            for neighbor in self.graph.get(node, set()):
                if neighbor not in visited:
                    visited.add(neighbor)
                    max_d = max(max_d, _dfs(neighbor, depth + 1))
            return max_d

        return _dfs(rule_id, 0)

    def topological_sort(self) -> list[int]:
        """Return rules in topological order (dependencies first).

        Raises:
            CyclicDependencyError: If the graph has cycles.
        """
        has_cyc, cycles = self.has_cycles()
        if has_cyc:
            cycle_str = ", ".join("→".join(map(str, cycle)) for cycle in cycles)
            raise CyclicDependencyError(f"Circular rule dependencies detected: {cycle_str}")

        visited: set[int] = set()
        order: list[int] = []

        def visit(node: int) -> None:
            if node in visited:
                return
            visited.add(node)
            for dep in self.graph.get(node, set()):
                visit(dep)
            order.append(node)

        for rule_id in self.graph:
            visit(rule_id)

        return order
