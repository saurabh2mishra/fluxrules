"""No-operation tracer for when observability is not needed."""

from __future__ import annotations

from typing import Any

from fluxrules.ports.observability import TracerPort


class NoopTracer(TracerPort):
    """A no-op tracer that discards all tracing data."""

    def on_evaluation_start(self, ruleset_id: int | str) -> None:
        """Called at the start of ruleset evaluation (no-op)."""

    def on_evaluation_end(self, ruleset_id: int | str, matched_count: int) -> None:
        """Called at the end of ruleset evaluation (no-op)."""

    def start_span(self, name: str, attributes: dict[str, Any] | None = None) -> Any:
        """Start a span (no-op)."""
        return None

    def end_span(self, span: Any) -> None:
        """End a span (no-op)."""

    def record_event(self, span: Any, name: str, attributes: dict[str, Any] | None = None) -> None:
        """Record an event (no-op)."""
