# backend/tests/test_dependency_graph.py
import pytest
from unittest.mock import MagicMock
from app.engine.dependency_graph import DependencyGraphBuilder
from app.models.rule import Rule
import json

def test_extract_fields():
    db_mock = MagicMock()
    builder = DependencyGraphBuilder(db_mock)
    
    condition = {
        "type": "group",
        "op": "AND",
        "children": [
            {"type": "condition", "field": "amount", "op": ">", "value": 100},
            {"type": "condition", "field": "status", "op": "==", "value": "active"}
        ]
    }
    
    fields = builder._extract_fields(condition)
    assert "amount" in fields
    assert "status" in fields

def test_build_graph_with_shared_fields():
    db_mock = MagicMock()
    builder = DependencyGraphBuilder(db_mock)
    
    condition1 = json.dumps({"type": "condition", "field": "amount", "op": ">", "value": 100})
    condition2 = json.dumps({"type": "condition", "field": "amount", "op": "<", "value": 200})
    
    rule1 = Rule(id=1, name="Rule1", condition_dsl=condition1, enabled=True)
    rule2 = Rule(id=2, name="Rule2", condition_dsl=condition2, enabled=True)
    
    db_mock.query.return_value.filter.return_value.all.return_value = [rule1, rule2]
    
    graph = builder.build_graph()
    
    assert len(graph["nodes"]) == 2
    assert len(graph["edges"]) == 1