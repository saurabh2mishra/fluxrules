"""Dependency graph builder for rules - no database required.

Builds a graph of rules that share condition fields, useful for
impact analysis and visualization.
"""

from __future__ import annotations

from typing import Any


class DependencyGraphBuilder:
    """Build a dependency graph from rule dicts (no DB needed)."""

    def build_graph(self, rules: list[dict[str, Any]]) -> dict[str, Any]:
        """Build a graph of rules connected by shared condition fields.

        Args:
            rules: List of rule dicts with ``id``, ``name``, ``group``,
                   ``priority``, and ``condition_dsl`` keys.

        Returns:
            Dict with ``nodes`` and ``edges`` lists.
        """
        nodes = []
        edges = []

        for rule in rules:
            nodes.append(
                {
                    "id": rule.get("id"),
                    "name": rule.get("name"),
                    "group": rule.get("group", "default"),
                    "priority": rule.get("priority", 0),
                }
            )

        for i, rule1 in enumerate(rules):
            fields1 = self._extract_fields(rule1.get("condition_dsl") or {})
            for rule2 in rules[i + 1 :]:
                fields2 = self._extract_fields(rule2.get("condition_dsl") or {})
                shared_fields = fields1 & fields2
                if shared_fields:
                    edges.append(
                        {
                            "source": rule1.get("id"),
                            "target": rule2.get("id"),
                            "shared_fields": sorted(shared_fields),
                        }
                    )

        return {"nodes": nodes, "edges": edges}

    def _extract_fields(self, condition: dict[str, Any]) -> set[str]:
        fields: set[str] = set()
        if not condition:
            return fields

        if condition.get("type") == "condition":
            field = condition.get("field")
            if field:
                fields.add(field)
        elif condition.get("type") == "group":
            for child in condition.get("children", []):
                fields.update(self._extract_fields(child))

        return fields
