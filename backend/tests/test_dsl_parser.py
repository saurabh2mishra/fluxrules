# backend/tests/test_dsl_parser.py
import pytest
from app.engine.dsl_parser import DSLParser

def test_parse_simple_condition():
    parser = DSLParser()
    dsl = {
        "type": "condition",
        "field": "amount",
        "op": ">",
        "value": 100
    }
    result = parser.parse(dsl)
    assert "amount" in result
    assert "100" in result

def test_parse_and_group():
    parser = DSLParser()
    dsl = {
        "type": "group",
        "op": "AND",
        "children": [
            {"type": "condition", "field": "amount", "op": ">", "value": 100},
            {"type": "condition", "field": "status", "op": "==", "value": "active"}
        ]
    }
    result = parser.parse(dsl)
    assert "amount" in result
    assert "status" in result

def test_parse_nested_groups():
    parser = DSLParser()
    dsl = {
        "type": "group",
        "op": "OR",
        "children": [
            {
                "type": "group",
                "op": "AND",
                "children": [
                    {"type": "condition", "field": "a", "op": ">", "value": 1},
                    {"type": "condition", "field": "b", "op": "<", "value": 10}
                ]
            },
            {"type": "condition", "field": "c", "op": "==", "value": "test"}
        ]
    }
    result = parser.parse(dsl)
    assert result is not None