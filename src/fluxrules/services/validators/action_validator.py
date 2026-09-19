"""Action validator - checks if action handlers exist."""

from __future__ import annotations

from typing import Any

from .base import ValidationResult, Validator


class ActionValidator(Validator):
    """Validates that referenced actions exist in the action registry.

    Checks:
    - Action field is not empty
    - Action handler is registered (if registry available)
    """

    def __init__(self, action_registry: dict[str, Any] | None = None):
        """Initialize with optional action registry.

        Args:
            action_registry: Dictionary of registered action handlers
        """
        self.action_registry = action_registry or {}

    def validate(self, rule_data: dict[str, Any]) -> ValidationResult:
        """Validate action."""
        result = ValidationResult()

        action = rule_data.get("action")
        if not action:
            result.add_error(
                "missing_action",
                "Action field is required",
                field="action",
            )
            return result

        if not isinstance(action, str):
            result.add_error(
                "invalid_action_type",
                f"Action must be string, got {type(action).__name__}",
                field="action",
            )
            return result

        # Check if action exists in registry
        self._check_action_exists(action, result)

        return result

    def _check_action_exists(self, action: str, result: ValidationResult) -> None:
        """Check if action is registered."""
        if not self.action_registry:
            # No registry, skip check
            return

        # Parse action name (might be "action_name" or "module.action_name")
        action_name = action.split("(")[0] if "(" in action else action
        action_name = action_name.split(":")[0] if ":" in action_name else action_name

        if action_name not in self.action_registry:
            result.add_warning(
                "unknown_action",
                f"Action '{action_name}' is not registered in the action registry",
                field="action",
                details={"registered_actions": list(self.action_registry.keys())},
            )

    @property
    def validator_name(self) -> str:
        """Return validator name."""
        return "ActionValidator"
