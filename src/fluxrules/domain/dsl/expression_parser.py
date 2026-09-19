"""DSL parser for FluxRules rule definitions.

Translates a tree of condition / group nodes expressed as plain
dictionaries into a Python-expression string that the rule engine
can compile and evaluate.

Example::

    >>> parser = DSLParser()
    >>> parser.parse({"type": "condition", "field": "age", "op": ">", "value": 18})
    'm.age > 18'
"""

from __future__ import annotations

from typing import Any


class DSLParser:
    """Parse DSL node trees into evaluable expression strings."""

    def parse(self, dsl: dict[str, Any]) -> str:
        """Parse a top-level DSL node.

        Args:
            dsl: Dictionary with at least a ``type`` key (``"condition"`` or
                ``"group"``).

        Returns:
            A Python-expression string suitable for ``eval`` / ``compile``.
        """
        return self._parse_node(dsl)

    def _parse_node(self, node: dict[str, Any]) -> str:
        """Dispatch to the correct parser based on node type.

        Args:
            node: DSL node with a ``type`` key.

        Returns:
            Parsed expression string, or ``""`` for unknown types.
        """
        if node["type"] == "condition":
            return self._parse_condition(node)
        elif node["type"] == "group":
            return self._parse_group(node)
        return ""

    def _parse_condition(self, node: dict[str, Any]) -> str:
        """Parse a single condition node into an expression.

        Args:
            node: Must contain ``field``, ``op``, and ``value`` keys.

        Returns:
            Expression string like ``"m.age > 18"``.
        """
        field: str = node["field"]
        op: str = node["op"]
        value: Any = node["value"]

        op_map: dict[str, str] = {
            ">": "m.{} > {}",
            ">=": "m.{} >= {}",
            "<": "m.{} < {}",
            "<=": "m.{} <= {}",
            "==": "m.{} == {}",
            "!=": "m.{} != {}",
        }

        template = op_map.get(op, "m.{} == {}")
        return template.format(field, repr(value))

    def _parse_group(self, node: dict[str, Any]) -> str:
        """Parse a group node (AND / OR) by recursing into children.

        Args:
            node: Must contain ``op`` (``"AND"`` or ``"OR"``) and optional
                ``children`` list.

        Returns:
            Combined expression string.
        """
        op: str = node["op"]
        children: list[dict[str, Any]] = node.get("children", [])

        parsed_children: list[str] = [self._parse_node(child) for child in children]

        if op == "AND":
            return " & ".join(f"({c})" for c in parsed_children)
        elif op == "OR":
            return " | ".join(f"({c})" for c in parsed_children)

        return ""
