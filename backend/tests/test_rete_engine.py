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