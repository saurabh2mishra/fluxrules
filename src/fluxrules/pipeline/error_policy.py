"""Error handling policies for fact pipelines.

Replaces magic ``on_error="skip"`` strings with a typed, granular policy. A
policy decides - per exception type - whether to fail fast, skip the record,
retry the transform, or substitute a fallback value.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

__all__ = [
    "ErrorAction",
    "ErrorDecision",
    "ErrorPolicy",
]


class ErrorAction(str, Enum):
    """What to do when a transform raises.

    Members:
        FAIL: Re-raise the error (fail fast).
        SKIP: Drop the record silently and stop processing it.
        RETRY: Retry the failing transform up to ``max_retries`` times.
        FALLBACK: Substitute a fallback fact and continue.
    """

    FAIL = "fail"
    SKIP = "skip"
    RETRY = "retry"
    FALLBACK = "fallback"


@dataclass(frozen=True)
class ErrorDecision:
    """Outcome of consulting an :class:`ErrorPolicy` for a given error."""

    action: ErrorAction
    fallback: dict[str, Any] | None = None


@dataclass
class ErrorPolicy:
    """Map exception types to :class:`ErrorAction` decisions.

    Resolution order:

    1. Exact type match in ``routes``.
    2. The most specific base-class match in ``routes`` (MRO walk).
    3. ``default`` if nothing matches.

    Example:
        >>> policy = ErrorPolicy(
        ...     default=ErrorAction.FAIL,
        ...     routes={ValueError: ErrorAction.SKIP},
        ... )
        >>> policy.decide(ValueError("bad")).action
        <ErrorAction.SKIP: 'skip'>
    """

    default: ErrorAction = ErrorAction.FAIL
    routes: dict[type[Exception], ErrorAction] = field(default_factory=dict)
    max_retries: int = 1
    retry_backoff: float = 0.0
    fallback_factory: Callable[[dict[str, Any], Exception], dict[str, Any]] | None = None

    def decide(self, error: Exception, fact: dict[str, Any] | None = None) -> ErrorDecision:
        """Resolve the action for ``error`` and build an :class:`ErrorDecision`."""
        action = self._resolve_action(error)
        fallback: dict[str, Any] | None = None
        if action is ErrorAction.FALLBACK:
            if self.fallback_factory is None:
                # No factory configured: degrade to FAIL so errors are visible.
                return ErrorDecision(action=ErrorAction.FAIL)
            fallback = self.fallback_factory(fact or {}, error)
        return ErrorDecision(action=action, fallback=fallback)

    def _resolve_action(self, error: Exception) -> ErrorAction:
        """Find the most specific configured action for ``error``."""
        error_type = type(error)
        if error_type in self.routes:
            return self.routes[error_type]
        for base in error_type.__mro__[1:]:
            if base in self.routes:
                return self.routes[base]  # type: ignore[index]
        return self.default

    def sleep_before_retry(self, attempt: int) -> None:
        """Sleep ``retry_backoff * attempt`` seconds before a retry attempt."""
        if self.retry_backoff > 0:
            time.sleep(self.retry_backoff * attempt)

    @classmethod
    def fail_fast(cls) -> ErrorPolicy:
        """Policy that re-raises every error (the safe default)."""
        return cls(default=ErrorAction.FAIL)

    @classmethod
    def skip_all(cls) -> ErrorPolicy:
        """Policy that drops every failing record."""
        return cls(default=ErrorAction.SKIP)
