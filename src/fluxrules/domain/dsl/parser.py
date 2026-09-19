"""Parse raw DSL dicts into strongly-typed AST nodes.

Producing a typed AST lets the PHREAK network builder and other consumers
process conditions through visitors instead of handling raw dicts directly.
"""

from __future__ import annotations

from typing import Any

from fluxrules.domain.dsl import (
    AccumulateNode,
    ConditionNode,
    CrossFactJoinNode,
    DSLNode,
    ExistsNode,
    GroupNode,
    NotNode,
    SequenceNode,
)
from fluxrules.exceptions import DSLParseError


class DSLParser:
    """Parse dict-based DSL into typed AST.

    Usage:
        parser = DSLParser()
        ast = parser.parse({"type": "condition", "field": "age", "op": ">", "value": 18})
        # ast is now a ConditionNode; can be visited by any DSLVisitor
    """

    def parse(self, dsl_dict: dict[str, Any]) -> DSLNode:
        """Parse a DSL dict into an AST node.

        Args:
            dsl_dict: Raw condition DSL dictionary.

        Returns:
            Typed DSLNode representing the condition tree.

        Raises:
            DSLParseError: If the DSL is malformed.
        """
        if not dsl_dict:
            raise DSLParseError("Empty DSL dict", detail="None or empty dict provided")
        try:
            return self._parse_node(dsl_dict)
        except DSLParseError:
            raise
        except (KeyError, TypeError, ValueError) as e:
            raise DSLParseError(f"Invalid DSL: {e}", detail=str(dsl_dict)) from e

    def _parse_node(self, node_dict: dict[str, Any]) -> DSLNode:
        """Dispatch to appropriate parser based on node type."""
        node_type = node_dict.get("type")

        if node_type == "condition":
            return self._parse_condition(node_dict)
        elif node_type == "group":
            return self._parse_group(node_dict)
        elif node_type == "not":
            return self._parse_not(node_dict)
        elif node_type == "exists":
            return self._parse_exists(node_dict)
        elif node_type == "accumulate":
            return self._parse_accumulate(node_dict)
        elif node_type == "sequence":
            return self._parse_sequence(node_dict)
        elif node_type == "cross_fact_join":
            return self._parse_cross_fact_join(node_dict)
        else:
            raise DSLParseError(
                f"Unknown DSL node type: {node_type}",
                detail=str(node_dict),
            )

    def _parse_condition(self, d: dict[str, Any]) -> ConditionNode:
        field = d.get("field")
        op = d.get("op")
        if not field or not op:
            raise DSLParseError(
                "Condition node requires 'field' and 'op'",
                detail=str(d),
            )
        return ConditionNode(
            field=field,
            operator=op,
            value=d.get("value"),
        )

    def _parse_group(self, d: dict[str, Any]) -> GroupNode:
        children_raw = d.get("children") or d.get("conditions") or []
        logic = (d.get("logic") or d.get("op", "AND")).upper()
        children = tuple(self._parse_node(child) for child in children_raw)
        return GroupNode(logic=logic, children=children)

    def _parse_not(self, d: dict[str, Any]) -> NotNode:
        inner_dict = d.get("condition")
        inner_list = d.get("conditions", [])

        if inner_dict:
            inner = self._parse_node(inner_dict)
            return NotNode(inner=inner)
        elif inner_list:
            children = tuple(self._parse_node(c) for c in inner_list)
            return NotNode(children=children)
        else:
            raise DSLParseError(
                "NOT node requires 'condition' or 'conditions' field",
                detail=str(d),
            )

    def _parse_exists(self, d: dict[str, Any]) -> ExistsNode:
        field = d.get("field")
        inner_dict = d.get("condition")
        inner = self._parse_node(inner_dict) if inner_dict else None
        return ExistsNode(field=field, inner=inner)

    def _parse_accumulate(self, d: dict[str, Any]) -> AccumulateNode:
        where_dict = d.get("where")
        where_node = self._parse_node(where_dict) if where_dict else None
        return AccumulateNode(
            source=d.get("source"),
            field=d.get("field"),
            aggregate=str(d.get("aggregate", "count")).lower(),
            operator=d.get("op", "=="),
            value=d.get("value"),
            where=where_node,
        )

    def _parse_sequence(self, d: dict[str, Any]) -> SequenceNode:
        steps_raw = d.get("steps", [])
        steps = tuple(self._parse_node(step) for step in steps_raw)
        return SequenceNode(
            source=d.get("source"),
            steps=steps,
        )

    def _parse_cross_fact_join(self, d: dict[str, Any]) -> CrossFactJoinNode:
        correlate_field = d.get("correlate_field")
        if not correlate_field:
            raise DSLParseError(
                "cross_fact_join requires 'correlate_field'",
                detail=str(d),
            )
        return CrossFactJoinNode(correlate_field=correlate_field)
