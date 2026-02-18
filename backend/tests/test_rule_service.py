# backend/tests/test_rule_service.py
import pytest
from unittest.mock import MagicMock
from app.services.rule_service import RuleService
from app.schemas.rule import RuleCreate

def test_create_rule():
    db_mock = MagicMock()
    service = RuleService(db_mock)
    
    rule_data = RuleCreate(
        name="TestRule",
        description="Test description",
        group="test_group",
        priority=10,
        enabled=True,
        condition_dsl={"type": "condition", "field": "amount", "op": ">", "value": 100},
        action="print('matched')"
    )
    
    rule = service.create_rule(rule_data, user_id=1)
    
    assert db_mock.add.call_count == 3  # Expect 3: rule, version, audit
    db_mock.commit.assert_called()

def test_list_rules():
    db_mock = MagicMock()
    service = RuleService(db_mock)
    
    db_mock.query.return_value.offset.return_value.limit.return_value.all.return_value = []
    
    rules = service.list_rules()
    assert isinstance(rules, list)