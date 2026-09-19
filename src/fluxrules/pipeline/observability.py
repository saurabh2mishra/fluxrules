"""Observability for fact pipelines.

Provides an extensible hook system and a metrics collector so pipelines stop
being black boxes. Hooks are invoked around every transform and around the
pipeline as a whole, enabling logging, metrics, and tracing without coupling
the core execution path to any particular backend.
"""

from __future__ import annotations

import logging
import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

if TYPE_CHECKING:
    from fluxrules.pipeline.base import Transform

__all__ = [
    "LoggingHook",
    "MetricsHook",
    "ObservabilityHook",
    "PipelineMetrics",
]


@runtime_checkable
class ObservabilityHook(Protocol):
    """Hook invoked at key points of pipeline execution.

    Implement any subset of these methods; the pipeline calls them
    defensively, so partial implementations are fine. The default
    :class:`Protocol` definitions are no-ops conceptually - concrete classes
    override what they care about.
    """

    def on_pipeline_start(self, pipeline_name: str, fact: dict[str, Any]) -> None:
        """Called before any transform runs."""
        ...

    def on_transform_start(self, transform: Transform, fact: dict[str, Any]) -> None:
        """Called before an individual transform runs."""
        ...

    def on_transform_end(self, transform: Transform, fact: dict[str, Any], duration: float) -> None:
        """Called after an individual transform completes successfully."""
        ...

    def on_transform_error(
        self, transform: Transform, fact: dict[str, Any], error: Exception
    ) -> None:
        """Called when an individual transform raises."""
        ...

    def on_pipeline_end(self, pipeline_name: str, fact: dict[str, Any], duration: float) -> None:
        """Called after the pipeline finishes successfully."""
        ...

    def on_pipeline_error(self, pipeline_name: str, fact: dict[str, Any], error: Exception) -> None:
        """Called when the pipeline fails."""
        ...


@dataclass
class PipelineMetrics:
    """Mutable collector of pipeline execution metrics.

    Aggregates counts and durations across many executions. Safe to share
    across calls of the same pipeline; snapshot with :meth:`as_dict`.
    """

    pipeline_runs: int = 0
    pipeline_errors: int = 0
    total_pipeline_duration: float = 0.0
    transform_invocations: dict[str, int] = field(default_factory=lambda: defaultdict(int))
    transform_errors: dict[str, int] = field(default_factory=lambda: defaultdict(int))
    transform_duration: dict[str, float] = field(default_factory=lambda: defaultdict(float))

    def record_transform(self, name: str, duration: float) -> None:
        """Record a successful transform invocation."""
        self.transform_invocations[name] += 1
        self.transform_duration[name] += duration

    def record_transform_error(self, name: str) -> None:
        """Record a transform failure."""
        self.transform_errors[name] += 1

    def record_pipeline(self, duration: float) -> None:
        """Record a successful pipeline run."""
        self.pipeline_runs += 1
        self.total_pipeline_duration += duration

    def record_pipeline_error(self) -> None:
        """Record a failed pipeline run."""
        self.pipeline_errors += 1

    @property
    def avg_pipeline_duration(self) -> float:
        """Mean pipeline duration in seconds (0.0 if no runs yet)."""
        if self.pipeline_runs == 0:
            return 0.0
        return self.total_pipeline_duration / self.pipeline_runs

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable snapshot of all metrics."""
        return {
            "pipeline_runs": self.pipeline_runs,
            "pipeline_errors": self.pipeline_errors,
            "total_pipeline_duration": self.total_pipeline_duration,
            "avg_pipeline_duration": self.avg_pipeline_duration,
            "transform_invocations": dict(self.transform_invocations),
            "transform_errors": dict(self.transform_errors),
            "transform_duration": dict(self.transform_duration),
        }


class MetricsHook:
    """Observability hook that records into a :class:`PipelineMetrics`.

    Example:
        >>> metrics = PipelineMetrics()
        >>> pipeline = FactPipeline([Flatten()], hooks=[MetricsHook(metrics)])
        >>> pipeline({"a": {"b": 1}})
        {'a.b': 1}
        >>> metrics.pipeline_runs
        1
    """

    def __init__(self, metrics: PipelineMetrics | None = None) -> None:
        self.metrics = metrics if metrics is not None else PipelineMetrics()

    def on_pipeline_start(self, pipeline_name: str, fact: dict[str, Any]) -> None:
        """No-op; metrics are recorded on completion."""

    def on_transform_start(self, transform: Transform, fact: dict[str, Any]) -> None:
        """No-op; metrics are recorded on completion."""

    def on_transform_end(self, transform: Transform, fact: dict[str, Any], duration: float) -> None:
        """Record a successful transform invocation."""
        self.metrics.record_transform(transform.metadata.name, duration)

    def on_transform_error(
        self, transform: Transform, fact: dict[str, Any], error: Exception
    ) -> None:
        """Record a transform failure."""
        self.metrics.record_transform_error(transform.metadata.name)

    def on_pipeline_end(self, pipeline_name: str, fact: dict[str, Any], duration: float) -> None:
        """Record a successful pipeline run."""
        self.metrics.record_pipeline(duration)

    def on_pipeline_error(self, pipeline_name: str, fact: dict[str, Any], error: Exception) -> None:
        """Record a failed pipeline run."""
        self.metrics.record_pipeline_error()


class LoggingHook:
    """Observability hook that emits structured log records.

    Uses the standard library :mod:`logging`; inject any logger or rely on the
    module default. Transform-level events log at ``DEBUG``; errors at
    ``ERROR``.
    """

    def __init__(self, logger: logging.Logger | None = None) -> None:
        self.logger = logger if logger is not None else logging.getLogger("fluxrules.pipeline")

    def on_pipeline_start(self, pipeline_name: str, fact: dict[str, Any]) -> None:
        """Log pipeline start."""
        self.logger.debug("pipeline_start name=%s keys=%s", pipeline_name, list(fact))

    def on_transform_start(self, transform: Transform, fact: dict[str, Any]) -> None:
        """Log transform start."""
        self.logger.debug("transform_start name=%s", transform.metadata.name)

    def on_transform_end(self, transform: Transform, fact: dict[str, Any], duration: float) -> None:
        """Log transform completion with duration."""
        self.logger.debug(
            "transform_end name=%s duration_ms=%.3f",
            transform.metadata.name,
            duration * 1000,
        )

    def on_transform_error(
        self, transform: Transform, fact: dict[str, Any], error: Exception
    ) -> None:
        """Log a transform error."""
        self.logger.error(
            "transform_error name=%s error=%s",
            transform.metadata.name,
            error,
        )

    def on_pipeline_end(self, pipeline_name: str, fact: dict[str, Any], duration: float) -> None:
        """Log pipeline completion with duration."""
        self.logger.debug("pipeline_end name=%s duration_ms=%.3f", pipeline_name, duration * 1000)

    def on_pipeline_error(self, pipeline_name: str, fact: dict[str, Any], error: Exception) -> None:
        """Log a pipeline error."""
        self.logger.error("pipeline_error name=%s error=%s", pipeline_name, error)


def _now() -> float:
    """Monotonic clock for duration measurement (testable seam)."""
    return time.perf_counter()
