"""Dependency graph tests"""

from fluxrules.utils.dependency_graph import DependencyGraphBuilder


def test_extract_fields():
    builder = DependencyGraphBuilder()
    condition = {
        "type": "group",
        "op": "AND",
        "children": [
            {"type": "condition", "field": "amount", "op": ">", "value": 100},
            {"type": "condition", "field": "status", "op": "==", "value": "active"},
        ],
    }
    fields = builder._extract_fields(condition)
    assert "amount" in fields
    assert "status" in fields


def test_build_graph_with_shared_fields():
    rules = [
        {
            "id": 1,
            "name": "Rule1",
            "condition_dsl": {
                "type": "condition",
                "field": "amount",
                "op": ">",
                "value": 100,
            },
        },
        {
            "id": 2,
            "name": "Rule2",
            "condition_dsl": {
                "type": "condition",
                "field": "amount",
                "op": "<",
                "value": 200,
            },
        },
    ]
    builder = DependencyGraphBuilder()
    graph = builder.build_graph(rules)
    assert len(graph["nodes"]) == 2
