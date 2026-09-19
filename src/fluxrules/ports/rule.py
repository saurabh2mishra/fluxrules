"""Port interface for rule abstraction."""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class RulePort(Protocol):
    """Abstract interface for a rule.

    Engines and services should program to this protocol
    rather than concrete Rule/EnhancedRule classes.
    """

    id: int | str
    name: str
    priority: int
    enabled: bool

    def is_active(self) -> bool:
        """Rule is enabled and active."""
        ...
