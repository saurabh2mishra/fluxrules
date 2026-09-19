"""Action plugin registry for custom rule actions.

This module provides a decorator-based registry system that enables any function
to be registered as an action with minimal boilerplate.

## Quick Start

```python
from fluxrules.plugins.actions import action

# Register a simple action
@action(
    name="send_slack_message",
    description="Send a message to Slack",
    category="notifications"
)
def send_slack_message(webhook_url: str, message: str) -> dict:
    # Your implementation
    return {"sent": True, "channel": "alerts"}

# Register an async action
@action(
    name="log_to_database",
    description="Log event to database",
    category="logging",
    async_handler=True
)
async def log_to_database(event_id: str, event_data: dict) -> dict:
    # Your async implementation
    return {"logged": True, "id": event_id}

# List all registered actions
print(action_registry.list_actions())

# Execute an action
result = action_registry.execute(
    "send_slack_message",
    webhook_url="https://...",
    message="Alert!")

# Execute async action
result = await action_registry.execute_async(
    "log_to_database",
    event_id="123",
    event_data={...})
```

## Advanced Usage

```python
# Get action metadata
metadata = action_registry.get_action_info("send_slack_message")

# Get actions by category
alerts = action_registry.get_actions_by_category("notifications")

# Get action signature (parameters and return type)
sig = action_registry.get_action_signature("send_slack_message")

# Validate parameters before execution
is_valid = action_registry.validate_parameters(
    "send_slack_message",
    webhook_url="https://...",
    message="Alert!")
```
"""

from __future__ import annotations

import inspect
import logging
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, get_type_hints

logger = logging.getLogger(__name__)


@dataclass
class ActionParameter:
    """Metadata about an action parameter."""

    name: str
    type_hint: type
    description: str = ""
    required: bool = True
    default: Any = None

    def __repr__(self) -> str:
        type_name = getattr(self.type_hint, "__name__", str(self.type_hint))
        return f"{self.name}: {type_name}"


@dataclass
class ActionMetadata:
    """Complete metadata about a registered action."""

    name: str
    function: Callable[..., Any]
    description: str
    category: str
    parameters: list[ActionParameter]
    return_type: type
    is_async: bool
    doc: str | None = None

    def __repr__(self) -> str:
        params = ", ".join(str(p) for p in self.parameters)
        async_label = "async " if self.is_async else ""
        return f"{async_label}{self.name}({params}) -> {self.return_type.__name__}"


class ActionRegistry:
    """Central registry for custom rule actions.

    Provides a decorator-based system to register any function as an action.
    Supports both sync and async functions with automatic parameter inspection
    and validation.

    ## Key Features

    - **Decorator-based registration**: Use @action() to register functions
    - **Automatic parameter inspection**: Extracts parameters from function
    - **Type hints support**: Validates and documents parameter types
    - **Async support**: Register and execute async functions
    - **Metadata extraction**: Automatically extracts docstrings and type info
    - **Parameter validation**: Validate arguments before execution
    - **Error handling**: Comprehensive error reporting
    - **Discovery**: List actions by category, get signatures, etc.

    ## Example

    ```python
    from fluxrules.plugins.actions import action_registry

    @action_registry.register(
        name="send_alert",
        description="Send alert to specified channel",
        category="alerts"
    )
    def send_alert(channel: str, message: str) -> dict:
        \"\"\"Send an alert message.

        Args:
            channel: Target channel (email, slack, webhook)
            message: Alert message to send
        \"\"\"
        # Implementation
        return {"sent": True}
    ```
    """

    def __init__(self) -> None:
        """Initialize the action registry."""
        self._actions: dict[str, ActionMetadata] = {}
        self._by_category: dict[str, list[str]] = {}

    def register(
        self,
        name: str,
        description: str = "",
        category: str = "general",
        async_handler: bool = False,
    ) -> Callable:
        """Decorator to register a custom action.

        Args:
            name: Unique action name (e.g., "send_slack_message")
            description: Human-readable description of what the action does
            category: Category for grouping actions
            async_handler: Set to True if the function is async

        Returns:
            Decorator function

        Example:
            ```python
            @action_registry.register(
                name="slack_notify",
                description="Send notification to Slack",
                category="notifications"
            )
            def slack_notify(webhook_url: str, message: str) -> dict:
                # Implementation
                return {"sent": True}
            ```
        """

        def decorator(func: Callable) -> Callable:
            # Extract metadata from function
            metadata = self._extract_metadata(
                func=func,
                name=name,
                description=description,
                category=category,
                is_async=async_handler or inspect.iscoroutinefunction(func),
            )

            # Register
            self._actions[name] = metadata
            self._by_category.setdefault(category, []).append(name)

            logger.info(f"Registered action: {name} | {description} | category={category}")

            return func

        return decorator

    def _extract_metadata(
        self,
        func: Callable,
        name: str,
        description: str,
        category: str,
        is_async: bool,
    ) -> ActionMetadata:
        """Extract metadata from a function."""
        # Get type hints
        type_hints = get_type_hints(func) if hasattr(func, "__annotations__") else {}

        # Extract parameters
        sig = inspect.signature(func)
        parameters = []

        for param_name, param in sig.parameters.items():
            if param_name in ("self", "cls"):
                continue

            param_type = type_hints.get(param_name, Any)
            has_default = param.default != inspect.Parameter.empty
            default_value = param.default if has_default else None

            parameters.append(
                ActionParameter(
                    name=param_name,
                    type_hint=param_type,
                    required=not has_default,
                    default=default_value,
                )
            )

        # Get return type
        return_type = type_hints.get("return", Any)

        return ActionMetadata(
            name=name,
            function=func,
            description=description,
            category=category,
            parameters=parameters,
            return_type=return_type,
            is_async=is_async,
            doc=inspect.getdoc(func),
        )

    def get(self, name: str) -> ActionMetadata | None:
        """Get action metadata by name.

        Args:
            name: Action name

        Returns:
            ActionMetadata if found, None otherwise
        """
        return self._actions.get(name)

    def has(self, name: str) -> bool:
        """Check if an action is registered.

        Args:
            name: Action name

        Returns:
            True if action exists
        """
        return name in self._actions

    def list_actions(cls) -> list[str]:
        """List all registered action names."""
        return list(cls._actions.keys())

    def list_actions_info(self) -> list[dict[str, Any]]:
        """Get information about all registered actions for UI display."""
        return [
            {
                "name": info.name,
                "description": info.description,
                "category": info.category,
                "async": info.is_async,
                "parameters": [
                    {
                        "name": p.name,
                        "type": getattr(p.type_hint, "__name__", str(p.type_hint)),
                        "required": p.required,
                        "default": p.default,
                    }
                    for p in info.parameters
                ],
                "return_type": getattr(info.return_type, "__name__", str(info.return_type)),
            }
            for info in self._actions.values()
        ]

    def get_actions_by_category(self, category: str) -> list[ActionMetadata]:
        """Get all actions in a category."""
        action_names = self._by_category.get(category, [])
        return [self._actions[name] for name in action_names]

    def get_action_signature(self, name: str) -> str | None:
        """Get the function signature of an action."""
        metadata = self.get(name)
        if not metadata:
            return None
        return str(metadata)

    def validate_parameters(self, action_name: str, **kwargs: Any) -> tuple[bool, str]:
        """Validate parameters for an action."""
        metadata = self.get(action_name)
        if not metadata:
            return False, f"Unknown action: {action_name}"

        # Check required parameters
        for param in metadata.parameters:
            if param.required and param.name not in kwargs:
                return False, f"Missing required parameter: {param.name}"

        # Check for extra parameters
        valid_names = {p.name for p in metadata.parameters}
        extra = set(kwargs.keys()) - valid_names
        if extra:
            return False, f"Unknown parameters: {', '.join(extra)}"

        return True, ""

    def execute(self, action_name: str, **kwargs: Any) -> dict[str, Any]:
        """Execute a registered sync action."""
        metadata = self.get(action_name)
        if not metadata:
            available = list(self._actions.keys())
            raise ValueError(f"Unknown action: {action_name}. Available: {available}")

        if metadata.is_async:
            raise ValueError(f"Action '{action_name}' is async. Use execute_async() instead.")

        # Validate parameters
        is_valid, error = self.validate_parameters(action_name, **kwargs)
        if not is_valid:
            raise ValueError(f"Parameter validation failed: {error}")

        try:
            logger.debug(f"Executing action: {action_name} with {kwargs}")
            result = metadata.function(**kwargs)
            logger.info(f"Action succeeded: {action_name}")
            return {
                "success": True,
                "action": action_name,
                "result": result,
            }
        except Exception as e:
            logger.error(f"Action failed: {action_name}: {e}", exc_info=True)
            return {
                "success": False,
                "action": action_name,
                "error": str(e),
            }

    async def execute_async(self, action_name: str, **kwargs: Any) -> dict[str, Any]:
        """Execute a registered async action."""
        metadata = self.get(action_name)
        if not metadata:
            available = list(self._actions.keys())
            raise ValueError(f"Unknown action: {action_name}. Available: {available}")

        if not metadata.is_async:
            raise ValueError(f"Action '{action_name}' is not async. Use execute() instead.")

        # Validate parameters
        is_valid, error = self.validate_parameters(action_name, **kwargs)
        if not is_valid:
            raise ValueError(f"Parameter validation failed: {error}")

        try:
            logger.debug(f"Executing async action: {action_name} with {kwargs}")
            result = await metadata.function(**kwargs)
            logger.info(f"Async action succeeded: {action_name}")
            return {
                "success": True,
                "action": action_name,
                "result": result,
            }
        except Exception as e:
            logger.error(f"Async action failed: {action_name}: {e}", exc_info=True)
            return {
                "success": False,
                "action": action_name,
                "error": str(e),
            }

    def reset(self) -> None:
        """Reset registry (for testing)."""
        self._actions.clear()
        self._by_category.clear()
        logger.info("Action registry reset")


# Global registry instance
action_registry = ActionRegistry()


# Convenience function for decorator
def action(
    name: str,
    description: str = "",
    category: str = "general",
    async_handler: bool = False,
) -> Callable:
    """Convenience decorator for registering actions.

    This is a shorthand for `action_registry.register()`.

    Args:
        name: Unique action name
        description: Human-readable description
        category: Category for grouping
        async_handler: Set to True for async functions

    Example:
        ```python
        from fluxrules.plugins.actions import action

        @action(
            name="send_alert",
            description="Send alert notification",
            category="alerts"
        )
        def send_alert(message: str, channel: str = "email") -> dict:
            # Implementation
            return {"sent": True}
        ```
    """
    return action_registry.register(
        name=name,
        description=description,
        category=category,
        async_handler=async_handler,
    )
