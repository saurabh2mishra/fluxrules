# backend/tests/test_conflict_detector.py
import pytest
from unittest.mock import MagicMock
from app.services.conflict_detector import ConflictDetector
from app.models.rule import Rule
import json

def test_detect_duplicate_conditions():
    db_mock = MagicMock()
    detector = ConflictDetector(db_mock)
    
    condition = json.dumps({"type": "condition", "field": "amount", "op": ">", "value": 100})
    
    rule1 = Rule(id=1, name="Rule1", condition_dsl=condition, enabled=True)
    rule2 = Rule(id=2, name="Rule2", condition_dsl=condition, enabled=True)
    
    rules = [rule1, rule2]
    conflicts = detector._detect_duplicate_conditions(rules)
    
    assert len(conflicts) == 1
    assert conflicts[0]["type"] == "duplicate_condition"

def test_detect_priority_collisions():
    db_mock = MagicMock()
    detector = ConflictDetector(db_mock)
    
    rule1 = Rule(id=1, name="Rule1", group="group1", priority=10, enabled=True)
    rule2 = Rule(id=2, name="Rule2", group="group1", priority=10, enabled=True)
    
    rules = [rule1, rule2]
    conflicts = detector._detect_priority_collisions(rules)
    
    assert len(conflicts) == 1
    assert conflicts[0]["type"] == "priority_collision"