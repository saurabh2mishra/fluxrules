"""Tests for DSL AST nodes and parser."""

import pytest

from fluxrules.domain.dsl import (
    AccumulateNode,
    ConditionNode,
    CrossFactJoinNode,
    ExistsNode,
    GroupNode,
    NotNode,
    SequenceNode,
)
from fluxrules.domain.dsl.parser import DSLParser
from fluxrules.exceptions import DSLParseError


class TestDSLParser:
    """Test DSL parser produces correct AST."""

    def setup_method(self):
        self.parser = DSLParser()

    def test_parse_simple_condition(self):
        ast = self.parser.parse({"type": "condition", "field": "age", "op": ">", "value": 18})
        assert isinstance(ast, ConditionNode)
        assert ast.field == "age"
        assert ast.operator == ">"
        assert ast.value == 18
        assert ast.node_type == "condition"

    def test_parse_group_and(self):
        ast = self.parser.parse(
            {
                "type": "group",
                "op": "AND",
                "children": [
                    {"type": "condition", "field": "age", "op": ">", "value": 18},
                    {
                        "type": "condition",
                        "field": "status",
                        "op": "==",
                        "value": "active",
                    },
                ],
            }
        )
        assert isinstance(ast, GroupNode)
        assert ast.logic == "AND"
        assert len(ast.children) == 2
        assert isinstance(ast.children[0], ConditionNode)
        assert isinstance(ast.children[1], ConditionNode)

    def test_parse_group_or(self):
        ast = self.parser.parse(
            {
                "type": "group",
                "op": "OR",
                "children": [
                    {"type": "condition", "field": "x", "op": "==", "value": 1},
                    {"type": "condition", "field": "y", "op": "==", "value": 2},
                ],
            }
        )
        assert isinstance(ast, GroupNode)
        assert ast.logic == "OR"

    def test_parse_not_node(self):
        ast = self.parser.parse(
            {
                "type": "not",
                "condition": {
                    "type": "condition",
                    "field": "banned",
                    "op": "==",
                    "value": True,
                },
            }
        )
        assert isinstance(ast, NotNode)
        assert isinstance(ast.inner, ConditionNode)
        assert ast.inner.field == "banned"

    def test_parse_not_with_conditions_list(self):
        ast = self.parser.parse(
            {
                "type": "not",
                "conditions": [
                    {"type": "condition", "field": "a", "op": "==", "value": 1},
                    {"type": "condition", "field": "b", "op": "==", "value": 2},
                ],
            }
        )
        assert isinstance(ast, NotNode)
        assert len(ast.children) == 2

    def test_parse_exists_with_field(self):
        ast = self.parser.parse({"type": "exists", "field": "email"})
        assert isinstance(ast, ExistsNode)
        assert ast.field == "email"
        assert ast.inner is None

    def test_parse_exists_with_inner(self):
        ast = self.parser.parse(
            {
                "type": "exists",
                "condition": {"type": "condition", "field": "x", "op": ">", "value": 0},
            }
        )
        assert isinstance(ast, ExistsNode)
        assert isinstance(ast.inner, ConditionNode)

    def test_parse_accumulate(self):
        ast = self.parser.parse(
            {
                "type": "accumulate",
                "source": "orders",
                "field": "amount",
                "aggregate": "sum",
                "op": ">",
                "value": 1000,
            }
        )
        assert isinstance(ast, AccumulateNode)
        assert ast.source == "orders"
        assert ast.aggregate == "sum"
        assert ast.operator == ">"
        assert ast.value == 1000

    def test_parse_accumulate_with_where(self):
        ast = self.parser.parse(
            {
                "type": "accumulate",
                "source": "items",
                "aggregate": "count",
                "op": ">",
                "value": 5,
                "where": {
                    "type": "condition",
                    "field": "status",
                    "op": "==",
                    "value": "active",
                },
            }
        )
        assert isinstance(ast, AccumulateNode)
        assert isinstance(ast.where, ConditionNode)

    def test_parse_sequence(self):
        ast = self.parser.parse(
            {
                "type": "sequence",
                "source": "events",
                "steps": [
                    {
                        "type": "condition",
                        "field": "action",
                        "op": "==",
                        "value": "login",
                    },
                    {
                        "type": "condition",
                        "field": "action",
                        "op": "==",
                        "value": "purchase",
                    },
                ],
            }
        )
        assert isinstance(ast, SequenceNode)
        assert ast.source == "events"
        assert len(ast.steps) == 2

    def test_parse_cross_fact_join(self):
        ast = self.parser.parse(
            {
                "type": "cross_fact_join",
                "correlate_field": "user_id",
            }
        )
        assert isinstance(ast, CrossFactJoinNode)
        assert ast.correlate_field == "user_id"

    def test_parse_empty_raises(self):
        with pytest.raises(DSLParseError):
            self.parser.parse({})

    def test_parse_unknown_type_raises(self):
        with pytest.raises(DSLParseError, match="Unknown DSL node type"):
            self.parser.parse({"type": "unknown_node"})

    def test_parse_condition_missing_field_raises(self):
        with pytest.raises(DSLParseError):
            self.parser.parse({"type": "condition", "op": ">"})

    def test_parse_not_missing_inner_raises(self):
        with pytest.raises(DSLParseError):
            self.parser.parse({"type": "not"})

    def test_parse_cross_fact_join_missing_field_raises(self):
        with pytest.raises(DSLParseError):
            self.parser.parse({"type": "cross_fact_join"})

    def test_nested_group(self):
        ast = self.parser.parse(
            {
                "type": "group",
                "op": "AND",
                "children": [
                    {"type": "condition", "field": "a", "op": ">", "value": 1},
                    {
                        "type": "group",
                        "op": "OR",
                        "children": [
                            {"type": "condition", "field": "b", "op": "==", "value": 2},
                            {"type": "condition", "field": "c", "op": "==", "value": 3},
                        ],
                    },
                ],
            }
        )
        assert isinstance(ast, GroupNode)
        assert isinstance(ast.children[1], GroupNode)
        assert ast.children[1].logic == "OR"


class TestDSLNodeAccept:
    """Test visitor dispatch via accept()."""

    class MockVisitor:
        """Track which visit methods are called."""

        def __init__(self):
            self.visited = []

        def visit_condition(self, node):
            self.visited.append(("condition", node))
            return "cond"

        def visit_group(self, node):
            self.visited.append(("group", node))
            return "group"

        def visit_not(self, node):
            self.visited.append(("not", node))
            return "not"

        def visit_exists(self, node):
            self.visited.append(("exists", node))
            return "exists"

        def visit_accumulate(self, node):
            self.visited.append(("accumulate", node))
            return "accumulate"

        def visit_sequence(self, node):
            self.visited.append(("sequence", node))
            return "sequence"

        def visit_cross_fact_join(self, node):
            self.visited.append(("cross_fact_join", node))
            return "cross_fact_join"

    def test_condition_dispatches(self):
        visitor = self.MockVisitor()
        node = ConditionNode(field="x", operator="==", value=1)
        result = node.accept(visitor)
        assert result == "cond"
        assert visitor.visited[0][0] == "condition"

    def test_group_dispatches(self):
        visitor = self.MockVisitor()
        node = GroupNode(logic="AND", children=())
        result = node.accept(visitor)
        assert result == "group"

    def test_not_dispatches(self):
        visitor = self.MockVisitor()
        node = NotNode(inner=ConditionNode(field="x", operator="==", value=1))
        result = node.accept(visitor)
        assert result == "not"

    def test_exists_dispatches(self):
        visitor = self.MockVisitor()
        node = ExistsNode(field="email")
        result = node.accept(visitor)
        assert result == "exists"

    def test_accumulate_dispatches(self):
        visitor = self.MockVisitor()
        node = AccumulateNode()
        result = node.accept(visitor)
        assert result == "accumulate"

    def test_sequence_dispatches(self):
        visitor = self.MockVisitor()
        node = SequenceNode()
        result = node.accept(visitor)
        assert result == "sequence"

    def test_cross_fact_join_dispatches(self):
        visitor = self.MockVisitor()
        node = CrossFactJoinNode(correlate_field="id")
        result = node.accept(visitor)
        assert result == "cross_fact_join"
