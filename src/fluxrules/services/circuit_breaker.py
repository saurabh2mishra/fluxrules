"""Circuit breaker implementation for fault tolerance."""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import datetime
from enum import Enum
from typing import Any

from fluxrules.ports.circuit_breaker import CircuitBreakerPort

logger = logging.getLogger(__name__)


class CircuitState(Enum):
    CLOSED = "CLOSED"
    OPEN = "OPEN"
    HALF_OPEN = "HALF_OPEN"


class CircuitBreaker(CircuitBreakerPort):
    """Circuit breaker for fault tolerance.

    Pattern:
    CLOSED -> failures exceed threshold -> OPEN
    OPEN -> after timeout -> HALF_OPEN
    HALF_OPEN -> success -> CLOSED
    HALF_OPEN -> failure -> OPEN
    """

    def __init__(
        self,
        name: str,
        failure_threshold: int = 5,
        recovery_timeout_seconds: int = 60,
        expected_exception: type[BaseException] = Exception,
    ) -> None:
        self.name = name
        self.failure_threshold = failure_threshold
        self.recovery_timeout_seconds = recovery_timeout_seconds
        self.expected_exception = expected_exception

        self._failures = 0
        self._last_failure_time: datetime | None = None
        self._state = CircuitState.CLOSED

    def call(self, func: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
        """Execute function with circuit breaker protection."""
        if self._state == CircuitState.OPEN:
            if self._should_attempt_reset():
                self._state = CircuitState.HALF_OPEN
                logger.info(f"Circuit '{self.name}' entering HALF_OPEN state")
            else:
                raise RuntimeError(f"Circuit '{self.name}' is OPEN. Service unavailable.")

        try:
            result = func(*args, **kwargs)
            self._on_success()
            return result
        except self.expected_exception:
            self._on_failure()
            raise

    def get_state(self) -> str:
        """Return current state as string."""
        return self._state.value

    def reset(self) -> None:
        """Manually reset the circuit breaker."""
        self._failures = 0
        self._last_failure_time = None
        self._state = CircuitState.CLOSED
        logger.info(f"Circuit '{self.name}' manually reset to CLOSED")

    def _on_success(self) -> None:
        """Handle successful call."""
        self._failures = 0
        if self._state == CircuitState.HALF_OPEN:
            self._state = CircuitState.CLOSED
            logger.info(f"Circuit '{self.name}' recovered to CLOSED state")

    def _on_failure(self) -> None:
        """Handle failed call."""
        self._failures += 1
        self._last_failure_time = datetime.now()
        logger.warning(f"Circuit '{self.name}' failure {self._failures}/{self.failure_threshold}")

        if self._failures >= self.failure_threshold:
            self._state = CircuitState.OPEN
            logger.error(f"Circuit '{self.name}' opened after {self._failures} failures")

    def _should_attempt_reset(self) -> bool:
        """Check if recovery timeout has passed."""
        if self._last_failure_time is None:
            return True
        elapsed = (datetime.now() - self._last_failure_time).total_seconds()
        return elapsed >= self.recovery_timeout_seconds
