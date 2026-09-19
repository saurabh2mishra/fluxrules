"""Port interface for circuit breaker fault tolerance."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable
from typing import Any


class CircuitBreakerPort(ABC):
    """Abstract interface for circuit breaker pattern.

    Implementations protect external service calls from cascading failures.
    States: CLOSED (normal) -> OPEN (failing) -> HALF_OPEN (testing recovery)
    """

    @abstractmethod
    def call(self, func: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
        """Execute func with circuit breaker protection.

        - Tracks failures
        - Opens circuit if threshold exceeded
        - Returns default/cached value when open
        """
        ...

    @abstractmethod
    def get_state(self) -> str:
        """Return 'CLOSED', 'OPEN', or 'HALF_OPEN'."""
        ...

    @abstractmethod
    def reset(self) -> None:
        """Manually reset the circuit breaker."""
        ...
