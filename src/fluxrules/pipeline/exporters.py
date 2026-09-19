"""External exporters for FactPipeline observability (Prometheus, OpenTelemetry).

This module provides concrete implementations of the :class:`ObservabilityHook`
protocol for popular observability backends. Each exporter is independently
optional - import and use only what you need.

Supported backends:
    - **Prometheus**: Counter and histogram metrics via the ``prometheus_client`` library
    - **OpenTelemetry**: Traces and metrics via ``opentelemetry-api``

Example (Prometheus):
    >>> from fluxrules.pipeline import FactPipeline, Flatten
    >>> from fluxrules.pipeline.exporters import PrometheusHook
    >>> hook = PrometheusHook()
    >>> pipeline = FactPipeline([Flatten()], hooks=[hook])
    >>> pipeline({"a": {"b": 1}})
    {'a.b': 1}

Example (OpenTelemetry):
    >>> from fluxrules.pipeline import FactPipeline, Flatten
    >>> from fluxrules.pipeline.exporters import OpenTelemetryHook
    >>> hook = OpenTelemetryHook(service_name="my_app")
    >>> pipeline = FactPipeline([Flatten()], hooks=[hook])
    >>> pipeline({"a": {"b": 1}})
    {'a.b': 1}
"""

from __future__ import annotations

import contextlib
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from fluxrules.pipeline.base import Transform

__all__ = [
    "OpenTelemetryHook",
    "PrometheusHook",
]


class PrometheusHook:
    """Export FactPipeline metrics to Prometheus.

    Tracks pipeline runs, errors, transform invocations, and duration histograms.
    Requires ``prometheus_client`` to be installed.

    By default the hook registers metrics in the global Prometheus registry,
    caching them per ``(registry, namespace, subsystem)`` so repeated
    construction is safe (no duplicate-timeseries errors). Pass a custom
    ``registry`` for isolation (e.g., in tests or multi-tenant apps).

    Example:
        >>> from fluxrules.pipeline.exporters import PrometheusHook
        >>> hook = PrometheusHook(namespace="myapp")
        >>> # hook will auto-register Prometheus metrics
        >>> # Metrics available at: http://localhost:8000/metrics (if using prometheus_client.start_http_server)
    """

    # Class-level cache keyed by (id(registry), namespace, subsystem) so the
    # same collectors are reused across instances and module reloads.
    _metrics_cache: dict[tuple[int, str, str], tuple] = {}

    def __init__(
        self,
        namespace: str = "fluxrules",
        subsystem: str = "pipeline",
        registry: Any = None,
    ) -> None:
        """Initialize Prometheus exporter.

        Args:
            namespace: Prefix for all metric names (e.g., "myapp" → "myapp_pipeline_*")
            subsystem: Subsystem label for metrics
            registry: Optional ``CollectorRegistry`` to register metrics in.
                Defaults to the global ``prometheus_client.REGISTRY``.

        Raises:
            ImportError: If ``prometheus_client`` is not installed.
        """
        try:
            from prometheus_client import REGISTRY, Counter, Histogram
        except ImportError as e:
            raise ImportError(
                "PrometheusHook requires 'prometheus_client'. "
                "Install with: pip install prometheus_client"
            ) from e

        if registry is None:
            registry = REGISTRY

        # Cache key isolates metrics per registry + namespace + subsystem so
        # repeated construction reuses the already-registered collectors.
        cache_key = (id(registry), namespace, subsystem)

        if cache_key not in PrometheusHook._metrics_cache:
            full_prefix = f"{namespace}_{subsystem}"

            pipeline_runs_total = Counter(
                f"{full_prefix}_pipeline_runs_total",
                "Total number of pipeline runs",
                ["pipeline_name"],
                registry=registry,
            )
            pipeline_errors_total = Counter(
                f"{full_prefix}_pipeline_errors_total",
                "Total number of pipeline errors",
                ["pipeline_name"],
                registry=registry,
            )
            pipeline_duration_seconds = Histogram(
                f"{full_prefix}_pipeline_duration_seconds",
                "Pipeline execution duration in seconds",
                ["pipeline_name"],
                buckets=(0.001, 0.01, 0.05, 0.1, 0.5, 1.0, 5.0),
                registry=registry,
            )
            transform_invocations_total = Counter(
                f"{full_prefix}_transform_invocations_total",
                "Total number of transform invocations",
                ["transform_name"],
                registry=registry,
            )
            transform_errors_total = Counter(
                f"{full_prefix}_transform_errors_total",
                "Total number of transform errors",
                ["transform_name"],
                registry=registry,
            )
            transform_duration_seconds = Histogram(
                f"{full_prefix}_transform_duration_seconds",
                "Transform execution duration in seconds",
                ["transform_name"],
                buckets=(0.001, 0.01, 0.05, 0.1, 0.5, 1.0),
                registry=registry,
            )

            PrometheusHook._metrics_cache[cache_key] = (
                pipeline_runs_total,
                pipeline_errors_total,
                pipeline_duration_seconds,
                transform_invocations_total,
                transform_errors_total,
                transform_duration_seconds,
            )

        # Set instance attributes from cache
        (
            self._pipeline_runs_total,
            self._pipeline_errors_total,
            self._pipeline_duration_seconds,
            self._transform_invocations_total,
            self._transform_errors_total,
            self._transform_duration_seconds,
        ) = PrometheusHook._metrics_cache[cache_key]

    def on_pipeline_start(self, pipeline_name: str, fact: dict[str, Any]) -> None:
        """No-op; Prometheus metrics recorded on completion."""

    def on_transform_start(self, transform: Transform, fact: dict[str, Any]) -> None:
        """No-op; Prometheus metrics recorded on completion."""

    def on_transform_end(self, transform: Transform, fact: dict[str, Any], duration: float) -> None:
        """Record successful transform to Prometheus."""
        if self._transform_invocations_total is not None:
            self._transform_invocations_total.labels(transform_name=transform.metadata.name).inc()
            self._transform_duration_seconds.labels(transform_name=transform.metadata.name).observe(
                duration
            )

    def on_transform_error(
        self, transform: Transform, fact: dict[str, Any], error: Exception
    ) -> None:
        """Record transform error to Prometheus."""
        if self._transform_errors_total is not None:
            self._transform_errors_total.labels(transform_name=transform.metadata.name).inc()

    def on_pipeline_end(self, pipeline_name: str, fact: dict[str, Any], duration: float) -> None:
        """Record successful pipeline run to Prometheus."""
        if self._pipeline_runs_total is not None:
            self._pipeline_runs_total.labels(pipeline_name=pipeline_name).inc()
            self._pipeline_duration_seconds.labels(pipeline_name=pipeline_name).observe(duration)

    def on_pipeline_error(self, pipeline_name: str, fact: dict[str, Any], error: Exception) -> None:
        """Record pipeline error to Prometheus."""
        if self._pipeline_errors_total is not None:
            self._pipeline_errors_total.labels(pipeline_name=pipeline_name).inc()


class OpenTelemetryHook:
    """Export FactPipeline executions to OpenTelemetry as distributed traces.

    Each pipeline run becomes one span (``pipeline.<name>``); individual
    transforms are recorded as span events. Success and failure are reported via
    the native span status (``StatusCode.OK`` / ``StatusCode.ERROR``), and
    failures additionally call :meth:`record_exception`. Requires
    ``opentelemetry-api`` (and an SDK + exporter to actually emit spans).

    The hook is resilient: if the tracer is missing or misconfigured, callbacks
    degrade to no-ops rather than raising into the pipeline's execution path.

    Example:
        >>> from fluxrules.pipeline.exporters import OpenTelemetryHook
        >>> hook = OpenTelemetryHook(service_name="my_rule_engine")
        >>> # hook uses the globally-configured TracerProvider/exporter
        >>> # Traces appear in your configured OpenTelemetry backend
    """

    def __init__(
        self,
        service_name: str = "fluxrules-pipeline",
        version: str = "1.0.0",
    ) -> None:
        """Initialize OpenTelemetry exporter.

        Args:
            service_name: Service name for traces (e.g., "my_rule_engine")
            version: Service version

        Raises:
            ImportError: If OpenTelemetry is not installed.
        """
        try:
            from opentelemetry import trace
        except ImportError as e:
            raise ImportError(
                "OpenTelemetryHook requires OpenTelemetry. "
                "Install with: pip install opentelemetry-api opentelemetry-sdk"
            ) from e

        self.service_name = service_name
        self.version = version
        # NOTE: ``get_tracer`` takes the instrumenting library version as a
        # positional argument; it does not accept a ``version=`` keyword.
        self.tracer = trace.get_tracer(service_name, version)
        self._pipeline_span: Any = None

    def on_pipeline_start(self, pipeline_name: str, fact: dict[str, Any]) -> None:
        """Start a (non-current) span for the pipeline.

        We use :meth:`start_span` rather than ``start_as_current_span`` because
        the hook holds the span across multiple discrete callbacks rather than a
        single ``with`` block. The returned object is a real ``Span`` so we can
        set attributes and end it later.
        """
        try:
            span = self.tracer.start_span(f"pipeline.{pipeline_name}")
            span.set_attribute("pipeline.name", pipeline_name)
            span.set_attribute("fact.keys", list(fact.keys()))
            self._pipeline_span = span
        except Exception:  # pragma: no cover - defensive: misconfigured tracer
            # Graceful degradation if OpenTelemetry is misconfigured.
            self._pipeline_span = None

    def on_transform_start(self, transform: Transform, fact: dict[str, Any]) -> None:
        """Record transform start as an event on the pipeline span."""
        if self._pipeline_span is not None:
            with contextlib.suppress(Exception):  # pragma: no cover - defensive
                self._pipeline_span.add_event(
                    "transform.start",
                    {
                        "transform.name": transform.metadata.name,
                        "transform.version": transform.metadata.version,
                    },
                )

    def on_transform_end(self, transform: Transform, fact: dict[str, Any], duration: float) -> None:
        """Record successful transform completion as a span event."""
        if self._pipeline_span is not None:
            with contextlib.suppress(Exception):  # pragma: no cover - defensive
                self._pipeline_span.add_event(
                    "transform.end",
                    {
                        "transform.name": transform.metadata.name,
                        "duration_seconds": duration,
                    },
                )

    def on_transform_error(
        self, transform: Transform, fact: dict[str, Any], error: Exception
    ) -> None:
        """Record a transform error as a span event."""
        if self._pipeline_span is not None:
            with contextlib.suppress(Exception):  # pragma: no cover - defensive
                self._pipeline_span.add_event(
                    "transform.error",
                    {
                        "transform.name": transform.metadata.name,
                        "error.type": type(error).__name__,
                        "error.message": str(error),
                    },
                )

    def on_pipeline_end(self, pipeline_name: str, fact: dict[str, Any], duration: float) -> None:
        """Mark the span successful and end it."""
        if self._pipeline_span is not None:
            try:
                from opentelemetry.trace import Status, StatusCode

                self._pipeline_span.set_attribute("pipeline.duration_seconds", duration)
                self._pipeline_span.set_status(Status(StatusCode.OK))
                self._pipeline_span.end()
            except Exception:  # noqa: S110 - best-effort telemetry, defensive
                pass
            finally:
                self._pipeline_span = None

    def on_pipeline_error(self, pipeline_name: str, fact: dict[str, Any], error: Exception) -> None:
        """Record the exception, mark the span as errored, and end it."""
        if self._pipeline_span is not None:
            try:
                from opentelemetry.trace import Status, StatusCode

                self._pipeline_span.record_exception(error)
                self._pipeline_span.set_status(Status(StatusCode.ERROR, str(error)))
                self._pipeline_span.end()
            except Exception:  # noqa: S110 - best-effort telemetry, defensive
                pass
            finally:
                self._pipeline_span = None
