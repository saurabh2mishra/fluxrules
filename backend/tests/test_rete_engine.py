# backend/tests/test_rete_engine.py
import pytest
from unittest.mock import MagicMock
from app.engine.rete_engine import ReteEngine

def test_evaluate_simple_condition():
    db_mock = MagicMock()
    engine = ReteEngine(db_mock)
    
    condition = {
        "type": "condition",
        "field": "amount",
        "op": ">",
        "value": 100
    }
    
    event = {"amount": 150}
    assert engine._evaluate_condition(condition, event) == True
    
    event = {"amount": 50}
    assert engine._evaluate_condition(condition, event) == False

def test_evaluate_and_group():
    db_mock = MagicMock()
    engine = ReteEngine(db_mock)
    
    condition = {
        "type": "group",
        "op": "AND",
        "children": [
            {"type": "condition", "field": "amount", "op": ">", "value": 100},
            {"type": "condition", "field": "status", "op": "==", "value": "active"}
        ]
    }
    
    event = {"amount": 150, "status": "active"}
    assert engine._evaluate_condition(condition, event) == True
    
    event = {"amount": 150, "status": "inactive"}
    assert engine._evaluate_condition(condition, event) == False

def test_evaluate_or_group():
    db_mock = MagicMock()
    engine = ReteEngine(db_mock)
    
    condition = {
        "type": "group",
        "op": "OR",
        "children": [
            {"type": "condition", "field": "amount", "op": ">", "value": 100},
            {"type": "condition", "field": "status", "op": "==", "value": "active"}
        ]
    }
    
    event = {"amount": 50, "status": "active"}
    assert engine._evaluate_condition(condition, event) == True
    
    event = {"amount": 50, "status": "inactive"}
    assert engine._evaluate_condition(condition, event) == False

def test_evaluate_nested_groups():
    db_mock = MagicMock()
    engine = ReteEngine(db_mock)
    condition = {
        "type": "group",
        "op": "AND",
        "children": [
            {"type": "condition", "field": "amount", "op": ">", "value": 100},
            {
                "type": "group",
                "op": "OR",
                "children": [
                    {"type": "condition", "field": "status", "op": "==", "value": "active"},
                    {"type": "condition", "field": "priority", "op": ">=", "value": 5}
                ]
            }
        ]
    }
    event = {"amount": 150, "status": "inactive", "priority": 5}
    assert engine._evaluate_condition(condition, event) == True
    event = {"amount": 150, "status": "inactive", "priority": 4}
    assert engine._evaluate_condition(condition, event) == False

def test_evaluate_all_operators():
    db_mock = MagicMock()
    engine = ReteEngine(db_mock)
    # >
    assert engine._evaluate_condition({"type": "condition", "field": "a", "op": ">", "value": 1}, {"a": 2})
    # >=
    assert engine._evaluate_condition({"type": "condition", "field": "a", "op": ">=", "value": 2}, {"a": 2})
    # <
    assert engine._evaluate_condition({"type": "condition", "field": "a", "op": "<", "value": 3}, {"a": 2})
    # <=
    assert engine._evaluate_condition({"type": "condition", "field": "a", "op": "<=", "value": 2}, {"a": 2})
    # ==
    assert engine._evaluate_condition({"type": "condition", "field": "a", "op": "==", "value": 2}, {"a": 2})
    # !=
    assert engine._evaluate_condition({"type": "condition", "field": "a", "op": "!=", "value": 3}, {"a": 2})
    # in
    assert engine._evaluate_condition({"type": "condition", "field": "a", "op": "in", "value": [1,2,3]}, {"a": 2})
    # contains
    assert engine._evaluate_condition({"type": "condition", "field": "a", "op": "contains", "value": "foo"}, {"a": "foobar"})

def test_missing_field_returns_false():
    db_mock = MagicMock()
    engine = ReteEngine(db_mock)
    condition = {"type": "condition", "field": "missing", "op": "==", "value": 1}
    event = {"amount": 1}
    assert engine._evaluate_condition(condition, event) is False

def test_empty_group():
    db_mock = MagicMock()
    engine = ReteEngine(db_mock)
    condition = {"type": "group", "op": "AND", "children": []}
    event = {"a": 1}
    assert engine._evaluate_condition(condition, event) is True  # all([]) is True
    condition = {"type": "group", "op": "OR", "children": []}
    assert engine._evaluate_condition(condition, event) is False  # any([]) is False

def test_type_mismatch():
    db_mock = MagicMock()
    engine = ReteEngine(db_mock)
    condition = {"type": "condition", "field": "a", "op": ">", "value": 1}
    event = {"a": "not_a_number"}
    assert engine._evaluate_condition(condition, event) is False

def test_group_with_single_child():
    db_mock = MagicMock()
    engine = ReteEngine(db_mock)
    condition = {"type": "group", "op": "AND", "children": [
        {"type": "condition", "field": "a", "op": "==", "value": 1}
    ]}
    event = {"a": 1}
    assert engine._evaluate_condition(condition, event) is True

def test_deeply_nested_groups():
    db_mock = MagicMock()
    engine = ReteEngine(db_mock)
    condition = {"type": "group", "op": "AND", "children": [
        {"type": "group", "op": "OR", "children": [
            {"type": "group", "op": "AND", "children": [
                {"type": "condition", "field": "x", "op": "==", "value": 1}
            ]}
        ]}
    ]}
    event = {"x": 1}
    assert engine._evaluate_condition(condition, event) is True

def test_negative_case():
    db_mock = MagicMock()
    engine = ReteEngine(db_mock)
    condition = {"type": "condition", "field": "a", "op": "==", "value": 2}
    event = {"a": 1}
    assert engine._evaluate_condition(condition, event) is False