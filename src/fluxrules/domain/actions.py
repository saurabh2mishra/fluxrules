"""Type-safe action definitions and execution.

Provides structured, typed actions that replace raw string actions.
Supports pluggable executors and synchronous handlers for extensibility.

Usage:
    from fluxrules.domain.actions import Action, ActionType, ActionExecutionEngine

    # Create typed actions
    action = Action.flag_for_review("suspicious transaction")
    action = Action.notify("slack", "Alert: rule triggered")
    action = Action.webhook("https://api.example.com/hook")

    # Execute actions
    engine = ActionExecutionEngine()
    engine.register_handler("flag_for_review", my_handler)
    results = await engine.execute_actions([action])
"""

from __future__ import annotations

import logging
import time
from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class ActionType(Enum):
    """Built-in action types."""

    FLAG_FOR_REVIEW = "flag_for_review"
    AUTO_APPROVE = "auto_approve"
    AUTO_DENY = "auto_deny"
    NOTIFY = "notify"
    EXECUTE_WEBHOOK = "execute_webhook"
    CUSTOM = "custom"


@dataclass(frozen=True)
class Action:
    """Typed, immutable action.

    Actions are the output of rule evaluation. They represent
    structured commands that can be executed by handlers.
    """

    type: ActionType
    payload: dict[str, Any]
    priority: int = 0

    @classmethod
    def flag_for_review(cls, reason: str) -> Action:
        """Create a flag_for_review action."""
        return cls(
            type=ActionType.FLAG_FOR_REVIEW,
            payload={"reason": reason},
            priority=10,
        )

    @classmethod
    def auto_approve(cls, reason: str = "Automated approval") -> Action:
        """Create an auto_approve action."""
        return cls(
            type=ActionType.AUTO_APPROVE,
            payload={"reason": reason},
            priority=8,
        )

    @classmethod
    def auto_deny(cls, reason: str = "Automated denial") -> Action:
        """Create an auto_deny action."""
        return cls(
            type=ActionType.AUTO_DENY,
            payload={"reason": reason},
            priority=9,
        )

    @classmethod
    def notify(cls, channel: str, message: str) -> Action:
        """Create a notify action."""
        return cls(
            type=ActionType.NOTIFY,
            payload={"channel": channel, "message": message},
            priority=5,
        )

    @classmethod
    def webhook(cls, url: str, method: str = "POST", **kwargs: Any) -> Action:
        """Create a webhook action."""
        return cls(
            type=ActionType.EXECUTE_WEBHOOK,
            payload={"url": url, "method": method, **kwargs},
        )

    @classmethod
    def custom(cls, name: str, **kwargs: Any) -> Action:
        """Create a custom action."""
        return cls(
            type=ActionType.CUSTOM,
            payload={"name": name, **kwargs},
        )

    def to_dict(self) -> dict[str, Any]:
        """Convert to dict for serialization."""
        return {
            "type": self.type.value,
            "payload": self.payload,
            "priority": self.priority,
        }


def get_available_actions() -> list[dict[str, Any]]:
    """Get list of all available actions for UI display.

    Returns:
        List of action metadata dictionaries with name, description, and category.
    """
    return [
        {
            "name": "flag_for_review",
            "description": "Flag the event/transaction for manual review",
            "category": "transactions",
        },
        {
            "name": "auto_approve",
            "description": "Automatically approve the event/transaction",
            "category": "transactions",
        },
        {
            "name": "auto_deny",
            "description": "Automatically deny/reject the event/transaction",
            "category": "transactions",
        },
        {
            "name": "notify",
            "description": "Send notification to a channel (email, Slack, etc.)",
            "category": "alerts",
        },
        {
            "name": "webhook",
            "description": "Execute a webhook request",
            "category": "integration",
        },
    ]


# Action Execution Framework


class ActionExecutionError(Exception):
    """Raised when action execution fails."""

    def __init__(
        self,
        message: str,
        action: Action,
        cause: Exception | None = None,
    ):
        self.message = message
        self.action = action
        self.cause = cause
        super().__init__(message)


@dataclass
class ActionExecutionResult:
    """Result of action execution."""

    success: bool
    action: Action
    output: Any | None = None
    error: str | None = None
    duration_ms: float = 0.0

    def __repr__(self) -> str:
        status = "✓" if self.success else "✗"
        return f"{status} {self.action.type.value}: {self.output or self.error}"


class ActionExecutor(ABC):
    """Base class for custom action executors.

    Implement this to handle specific action types:

        class SlackNotifier(ActionExecutor):
            def can_execute(self, action: Action) -> bool:
                return action.type == ActionType.NOTIFY

            async def execute(self, action: Action) -> ActionExecutionResult:
                # Post to Slack...
                return ActionExecutionResult(success=True, action=action)
    """

    @abstractmethod
    def can_execute(self, action: Action) -> bool:
        """Check if this executor handles the action type."""
        ...

    @abstractmethod
    async def execute(self, action: Action) -> ActionExecutionResult:
        """Execute an action asynchronously."""
        ...


class ActionExecutionEngine:
    """Pluggable action execution engine with handlers and executors.

    Supports two registration mechanisms:
    1. Synchronous handlers (simple callables)
    2. Async executors (for I/O-bound actions)

    Usage:
        engine = ActionExecutionEngine()
        engine.register_handler("flag_for_review", lambda a: print(a.payload))
        results = await engine.execute_actions([action])
    """

    def __init__(self) -> None:
        self._executors: list[ActionExecutor] = []
        self._handlers: dict[str, Callable[[Action], Any]] = {}

    def register_executor(self, executor: ActionExecutor) -> None:
        """Register an async action executor."""
        self._executors.append(executor)
        logger.info(f"Registered action executor: {executor.__class__.__name__}")

    def register_handler(
        self,
        action_type: str,
        handler: Callable[[Action], Any],
    ) -> None:
        """Register a synchronous handler for a specific action type."""
        self._handlers[action_type] = handler
        logger.info(f"Registered handler for action: {action_type}")

    async def execute_actions(
        self,
        actions: list[Action],
    ) -> list[ActionExecutionResult]:
        """Execute multiple actions in priority order."""
        results = []
        for action in sorted(actions, key=lambda a: a.priority, reverse=True):
            result = await self.execute(action)
            results.append(result)
            if not result.success:
                logger.error(f"Action execution failed: {result}")
        return results

    async def execute(self, action: Action) -> ActionExecutionResult:
        """Execute a single action."""
        start = time.time()

        # Try handlers first (synchronous)
        handler = self._handlers.get(action.type.value)
        if handler:
            try:
                output = handler(action)
                return ActionExecutionResult(
                    success=True,
                    action=action,
                    output=output,
                    duration_ms=(time.time() - start) * 1000,
                )
            except Exception as e:
                return ActionExecutionResult(
                    success=False,
                    action=action,
                    error=str(e),
                    duration_ms=(time.time() - start) * 1000,
                )

        # Try async executors
        for executor in self._executors:
            if executor.can_execute(action):
                try:
                    result = await executor.execute(action)
                    result.duration_ms = (time.time() - start) * 1000
                    return result
                except Exception as e:
                    return ActionExecutionResult(
                        success=False,
                        action=action,
                        error=str(e),
                        duration_ms=(time.time() - start) * 1000,
                    )

        # No executor found
        return ActionExecutionResult(
            success=False,
            action=action,
            error=f"No executor for action type: {action.type.value}",
            duration_ms=(time.time() - start) * 1000,
        )

    def parse_action_string(self, action_str: str) -> Action:
        """Parse a string action into a typed Action.

        Supports format "action_type:param1:param2" or plain "action_type".

        Args:
            action_str: Action string from rule evaluation.

        Returns:
            Typed Action instance.
        """
        if ":" in action_str:
            action_type, remainder = action_str.split(":", 1)
            # For webhook URLs, keep the full remainder as a single param
            if action_type == "webhook":
                params = [remainder] if remainder else []
            else:
                params = remainder.split(":") if remainder else []
        else:
            action_type, params = action_str, []

        if action_type == "flag_for_review":
            reason = params[0] if params else "Rule matched"
            return Action.flag_for_review(reason)
        elif action_type == "auto_approve":
            reason = params[0] if params else "Automated approval"
            return Action.auto_approve(reason)
        elif action_type == "auto_deny":
            reason = params[0] if params else "Automated denial"
            return Action.auto_deny(reason)
        elif action_type == "notify":
            channel = params[0] if params else "default"
            message = params[1] if len(params) > 1 else "Rule matched"
            return Action.notify(channel, message)
        elif action_type == "webhook":
            url = params[0] if params else ""
            return Action.webhook(url)
        else:
            return Action.custom(action_type, params=params)
