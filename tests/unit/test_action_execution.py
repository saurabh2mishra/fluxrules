"""Tests for Action system and ActionExecutionEngine."""

import asyncio

import pytest

from fluxrules.domain.actions import (
    Action,
    ActionExecutionEngine,
    ActionExecutionResult,
    ActionExecutor,
    ActionType,
)


class TestAction:
    """Test Action creation and factory methods."""

    def test_flag_for_review(self):
        action = Action.flag_for_review("suspicious")
        assert action.type == ActionType.FLAG_FOR_REVIEW
        assert action.payload == {"reason": "suspicious"}
        assert action.priority == 10

    def test_auto_approve(self):
        action = Action.auto_approve("low risk")
        assert action.type == ActionType.AUTO_APPROVE
        assert action.payload == {"reason": "low risk"}

    def test_auto_deny(self):
        action = Action.auto_deny("high risk")
        assert action.type == ActionType.AUTO_DENY
        assert action.payload == {"reason": "high risk"}

    def test_notify(self):
        action = Action.notify("slack", "Alert!")
        assert action.type == ActionType.NOTIFY
        assert action.payload == {"channel": "slack", "message": "Alert!"}
        assert action.priority == 5

    def test_webhook(self):
        action = Action.webhook("https://example.com/hook", method="POST", timeout=30)
        assert action.type == ActionType.EXECUTE_WEBHOOK
        assert action.payload["url"] == "https://example.com/hook"
        assert action.payload["method"] == "POST"
        assert action.payload["timeout"] == 30

    def test_custom(self):
        action = Action.custom("send_sms", phone="+1234567890")
        assert action.type == ActionType.CUSTOM
        assert action.payload["name"] == "send_sms"
        assert action.payload["phone"] == "+1234567890"

    def test_to_dict(self):
        action = Action.flag_for_review("test")
        d = action.to_dict()
        assert d == {
            "type": "flag_for_review",
            "payload": {"reason": "test"},
            "priority": 10,
        }

    def test_action_is_immutable(self):
        action = Action.flag_for_review("test")
        with pytest.raises(Exception):
            action.type = ActionType.CUSTOM  # type: ignore


class TestActionExecutionEngine:
    """Test ActionExecutionEngine."""

    def test_register_handler(self):
        engine = ActionExecutionEngine()
        engine.register_handler("flag_for_review", lambda a: "handled")
        assert "flag_for_review" in engine._handlers

    def test_execute_with_handler(self):
        engine = ActionExecutionEngine()
        engine.register_handler("flag_for_review", lambda a: f"flagged: {a.payload['reason']}")

        action = Action.flag_for_review("fraud")
        result = asyncio.run(engine.execute(action))

        assert result.success is True
        assert result.output == "flagged: fraud"
        assert result.duration_ms >= 0

    def test_execute_handler_exception(self):
        engine = ActionExecutionEngine()
        engine.register_handler("notify", lambda a: 1 / 0)

        action = Action.notify("slack", "test")
        result = asyncio.run(engine.execute(action))

        assert result.success is False
        assert "division by zero" in result.error

    def test_execute_no_handler(self):
        engine = ActionExecutionEngine()
        action = Action.custom("unknown_action")
        result = asyncio.run(engine.execute(action))

        assert result.success is False
        assert "No executor" in result.error

    def test_execute_multiple_actions_priority_order(self):
        engine = ActionExecutionEngine()
        executed_order = []

        def track(action):
            executed_order.append(action.type.value)
            return "ok"

        engine.register_handler("flag_for_review", track)
        engine.register_handler("notify", track)

        actions = [
            Action.notify("slack", "msg"),  # priority 5
            Action.flag_for_review("reason"),  # priority 10
        ]
        results = asyncio.run(engine.execute_actions(actions))

        assert len(results) == 2
        # Higher priority executed first
        assert executed_order[0] == "flag_for_review"
        assert executed_order[1] == "notify"

    def test_register_executor(self):
        class MockExecutor(ActionExecutor):
            def can_execute(self, action):
                return action.type == ActionType.CUSTOM

            async def execute(self, action):
                return ActionExecutionResult(success=True, action=action, output="custom_handled")

        engine = ActionExecutionEngine()
        engine.register_executor(MockExecutor())

        action = Action.custom("test_action")
        result = asyncio.run(engine.execute(action))

        assert result.success is True
        assert result.output == "custom_handled"

    def test_parse_action_string_flag(self):
        engine = ActionExecutionEngine()
        action = engine.parse_action_string("flag_for_review:suspicious_activity")
        assert action.type == ActionType.FLAG_FOR_REVIEW
        assert action.payload["reason"] == "suspicious_activity"

    def test_parse_action_string_notify(self):
        engine = ActionExecutionEngine()
        action = engine.parse_action_string("notify:slack:Alert triggered")
        assert action.type == ActionType.NOTIFY
        assert action.payload["channel"] == "slack"
        assert action.payload["message"] == "Alert triggered"

    def test_parse_action_string_custom(self):
        engine = ActionExecutionEngine()
        action = engine.parse_action_string("send_email")
        assert action.type == ActionType.CUSTOM
        assert action.payload["name"] == "send_email"

    def test_parse_action_string_webhook(self):
        engine = ActionExecutionEngine()
        action = engine.parse_action_string("webhook:https://example.com")
        assert action.type == ActionType.EXECUTE_WEBHOOK
        assert action.payload["url"] == "https://example.com"
