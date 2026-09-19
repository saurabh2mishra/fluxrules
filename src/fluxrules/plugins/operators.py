"""Operator plugin registry for custom condition operators."""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

logger = logging.getLogger(__name__)


class OperatorRegistry:
    """Central registry for custom condition operators.

    Built-in operators are pre-registered. Users can register custom operators
    via the @OperatorRegistry.register decorator.
    """

    _operators: dict[str, Callable[..., bool]] = {}

    @classmethod
    def register(cls, name: str) -> Callable:
        """Decorator to register a custom operator.

        Usage:
            @OperatorRegistry.register("fuzzy_match")
            def fuzzy_match(fact, value, threshold=0.8):
                ...
        """

        def decorator(func: Callable[..., bool]) -> Callable[..., bool]:
            cls._operators[name] = func
            logger.info(f"Registered operator: {name}")
            return func

        return decorator

    @classmethod
    def get(cls, name: str) -> Callable[..., bool] | None:
        """Get a registered operator by name."""
        return cls._operators.get(name)

    @classmethod
    def has(cls, name: str) -> bool:
        """Check if an operator is registered."""
        return name in cls._operators

    @classmethod
    def list_operators(cls) -> list[str]:
        """List all registered operator names."""
        return list(cls._operators.keys())

    @classmethod
    def execute(cls, name: str, fact: Any, value: Any, **kwargs: Any) -> bool:
        """Execute a registered operator."""
        op = cls._operators.get(name)
        if op is None:
            raise ValueError(f"Unknown operator: {name}")
        return op(fact, value, **kwargs)

    @classmethod
    def reset(cls) -> None:
        """Reset registry (for testing)."""
        cls._operators.clear()
        cls._register_builtins()

    @classmethod
    def _register_builtins(cls) -> None:
        """Register built-in operators."""
        cls._operators.update(
            {
                "eq": lambda a, b, **kw: a == b,
                "neq": lambda a, b, **kw: a != b,
                "gt": lambda a, b, **kw: a > b,
                "gte": lambda a, b, **kw: a >= b,
                "lt": lambda a, b, **kw: a < b,
                "lte": lambda a, b, **kw: a <= b,
                "in": lambda a, b, **kw: a in b,
                "not_in": lambda a, b, **kw: a not in b,
                "contains": lambda a, b, **kw: b in a,
                "starts_with": lambda a, b, **kw: str(a).startswith(str(b)),
                "ends_with": lambda a, b, **kw: str(a).endswith(str(b)),
            }
        )


# Auto-register builtins on import
OperatorRegistry._register_builtins()
