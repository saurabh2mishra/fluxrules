"""Custom operator registration for domain-specific comparisons.

Allows users to define and register custom operators (e.g., "within_distance",
"fuzzy_match") that can be used in rule conditions alongside built-in operators.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from fluxrules.domain.errors import UnknownOperatorError


class OperatorRegistry:
    """Registry for custom operator functions.

    Usage::

        registry = OperatorRegistry()
        registry.register("within_range", lambda val, spec: spec[0] <= val <= spec[1])

        # Later, in condition evaluation:
        func = registry.get("within_range")
        result = func(42, [10, 50])  # True
    """

    def __init__(self) -> None:
        self._operators: dict[str, Callable[[Any, Any], bool]] = {}

    def register(self, name: str, func: Callable[[Any, Any], bool]) -> None:
        """Register a custom operator.

        Args:
            name: Operator name (e.g., "within_distance").
            func: A callable (event_value, rule_value) -> bool.
        """
        if not callable(func):
            raise TypeError(f"Operator function must be callable, got {type(func)}")
        self._operators[name] = func

    def unregister(self, name: str) -> None:
        """Remove a registered operator."""
        self._operators.pop(name, None)

    def get(self, name: str) -> Callable[[Any, Any], bool]:
        """Get an operator function by name.

        Raises:
            UnknownOperatorError: If the operator is not registered.
        """
        if name not in self._operators:
            raise UnknownOperatorError(
                f"Custom operator '{name}' not registered. "
                f"Registered: {sorted(self._operators.keys())}"
            )
        return self._operators[name]

    def has(self, name: str) -> bool:
        """Check if an operator is registered."""
        return name in self._operators

    def list_operators(self) -> list[str]:
        """List all registered operator names."""
        return sorted(self._operators.keys())

    def clear(self) -> None:
        """Remove all registered operators."""
        self._operators.clear()


# Module-level default registry
_default_registry = OperatorRegistry()


def get_operator_registry() -> OperatorRegistry:
    """Get the default operator registry."""
    return _default_registry


def register_operator(name: str, func: Callable[[Any, Any], bool]) -> None:
    """Register a custom operator on the default registry."""
    _default_registry.register(name, func)
