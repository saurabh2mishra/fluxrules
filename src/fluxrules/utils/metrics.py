"""Pluggable metrics interface for the core engine.

The API layer can inject a real collector (e.g. Prometheus).  By default a
no-op collector is used so the core library has zero observability
dependencies.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class MetricsCollector(Protocol):
    """Protocol that any metrics backend must satisfy."""

    def increment_events_processed(self) -> None:
        """Record that one event was processed."""
        ...

    def increment_rules_fired(self, count: int = 1) -> None:
        """Record that *count* rules were fired."""
        ...

    def observe_processing_time(self, seconds: float) -> None:
        """Record the processing time for an evaluation cycle."""
        ...

    def increment_comparison_metric(self, name: str) -> None:
        """Increment a named comparison counter (e.g. ``"eq"``)."""
        ...


class NullMetrics:
    """No-op metrics - used when no collector is configured."""

    def increment_events_processed(self) -> None:
        """No-op."""

    def increment_rules_fired(self, count: int = 1) -> None:
        """No-op."""

    def observe_processing_time(self, seconds: float) -> None:
        """No-op."""

    def increment_comparison_metric(self, name: str) -> None:
        """No-op."""


def _init_default_collector() -> MetricsCollector:
    """Initialize the default metrics collector.

    Attempts to load Prometheus from the API layer. Falls back gracefully to
    :class:`NullMetrics` if ``prometheus_client`` is not installed or if the
    API layer is unavailable (e.g., in a minimal pip install).

    This ensures metrics work out-of-the-box for both API and standalone usage.

    Returns:
        Either a :class:`PrometheusMetricsCollector` or :class:`NullMetrics`.
    """
    try:
        from fluxrules.api.utils.metrics import PrometheusMetricsCollector

        return PrometheusMetricsCollector(engine="fluxrules")
    except ImportError:
        # prometheus_client package not installed
        return NullMetrics()
    except ModuleNotFoundError:
        # fluxrules.api module not available
        return NullMetrics()


_collector: MetricsCollector = _init_default_collector()


def set_metrics(collector: MetricsCollector) -> None:
    """Replace the active metrics collector.

    Args:
        collector: Any object satisfying :class:`MetricsCollector`.
    """
    global _collector
    _collector = collector


def get_metrics() -> MetricsCollector:
    """Return the currently active metrics collector.

    Returns:
        The active :class:`MetricsCollector` instance.
    """
    return _collector
