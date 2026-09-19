"""Port interface for observability (tracing, metrics)."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class TracerPort(ABC):
    """Abstract interface for rule execution tracing."""

    @abstractmethod
    def on_evaluation_start(self, ruleset_id: int | str) -> None:
        """Called at the start of ruleset evaluation."""

    @abstractmethod
    def on_evaluation_end(self, ruleset_id: int | str, matched_count: int) -> None:
        """Called at the end of ruleset evaluation with the number of matched rules."""

    @abstractmethod
    def start_span(self, name: str, attributes: dict[str, Any] | None = None) -> Any:
        """Start a new trace span."""

    @abstractmethod
    def end_span(self, span: Any) -> None:
        """End a trace span."""

    @abstractmethod
    def record_event(self, span: Any, name: str, attributes: dict[str, Any] | None = None) -> None:
        """Record an event within a span."""
