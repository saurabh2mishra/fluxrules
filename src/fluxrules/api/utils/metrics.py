"""Prometheus-backed implementation of the core MetricsCollector protocol.

A single :class:`PrometheusMetricsCollector` instance is created at
startup and injected into ``fluxrules.core.metrics`` via ``set_metrics()``.
All engines then call ``get_metrics()`` uniformly - no engine imports
anything from this module directly.

The ``engine`` label on every instrument lets you distinguish which engine
(PHREAK, SIMPLE, …) generated each data point in Prometheus/Grafana.
"""

from __future__ import annotations

from prometheus_client import CollectorRegistry, Counter, Histogram

# Module-level registry and instruments, initialised once.
_registry: CollectorRegistry | None = None
_events_processed: Counter | None = None
_rules_fired: Counter | None = None
_processing_time: Histogram | None = None
_comparison_events: Counter | None = None

# Lightweight in-memory mirror used by the /metrics/dashboard JSON endpoint.
_dashboard_stats: dict[str, int | float] = {
    "events_processed": 0,
    "rules_fired": 0,
    "total_processing_time_ms": 0,
    "evaluation_count": 0,
    "comparison_type_mismatch": 0,
    "string_bool_coercions": 0,
    "strict_null_evaluations": 0,
}


def get_metrics_registry() -> CollectorRegistry:
    """Return (and lazily create) the shared Prometheus registry.

    Returns:
        The singleton :class:`CollectorRegistry` used for all instruments.
    """
    global _registry, _events_processed, _rules_fired, _processing_time, _comparison_events

    if _registry is None:
        _registry = CollectorRegistry()

        _events_processed = Counter(
            "fluxrules_events_processed_total",
            "Total number of events processed, labelled by engine",
            labelnames=["engine"],
            registry=_registry,
        )

        _rules_fired = Counter(
            "fluxrules_rules_fired_total",
            "Total number of rules fired, labelled by engine",
            labelnames=["engine"],
            registry=_registry,
        )

        _processing_time = Histogram(
            "fluxrules_event_processing_seconds",
            "Time spent processing events, labelled by engine",
            labelnames=["engine"],
            buckets=(0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0),
            registry=_registry,
        )

        _comparison_events = Counter(
            "fluxrules_comparison_events_total",
            "Comparison edge-case events (type_mismatch, string_bool_coercions, strict_null_evaluations)",
            labelnames=["kind"],
            registry=_registry,
        )

    return _registry


class PrometheusMetricsCollector:
    """Prometheus implementation of ``core.metrics.MetricsCollector``.

    Instantiate once and pass to ``fluxrules.core.metrics.set_metrics()``.
    Every engine that calls ``get_metrics()`` will then record real data.

    Args:
        engine: A short label identifying the engine (e.g. ``"PHREAK"``).
                Appears as the ``engine`` label on all Prometheus metrics.
    """

    def __init__(self, engine: str = "unknown") -> None:
        self.engine = engine
        # Ensure the registry (and instruments) exist before first use.
        get_metrics_registry()

    def increment_events_processed(self) -> None:
        """Increment the events-processed counter."""
        if _events_processed is not None:
            _events_processed.labels(engine=self.engine).inc()
        _dashboard_stats["events_processed"] += 1

    def increment_rules_fired(self, count: int = 1) -> None:
        """Increment the rules-fired counter by *count*.

        Args:
            count: Number of rules that fired in this evaluation cycle.
        """
        if _rules_fired is not None:
            _rules_fired.labels(engine=self.engine).inc(count)
        _dashboard_stats["rules_fired"] += count

    def observe_processing_time(self, seconds: float) -> None:
        """Record the processing duration for one evaluation cycle.

        Args:
            seconds: Wall-clock time in seconds.
        """
        if _processing_time is not None:
            _processing_time.labels(engine=self.engine).observe(seconds)
        _dashboard_stats["total_processing_time_ms"] += seconds * 1000
        _dashboard_stats["evaluation_count"] += 1

    def increment_comparison_metric(self, name: str) -> None:
        """Increment a named comparison edge-case counter.

        Args:
            name: One of ``"comparison_type_mismatch"``,
                ``"string_bool_coercions"``, or ``"strict_null_evaluations"``.
        """
        if _comparison_events is not None:
            _comparison_events.labels(kind=name).inc()
        if name in _dashboard_stats:
            _dashboard_stats[name] += 1


# Free functions used by the API event path (adapter, event routes, worker).
# They delegate to the global collector so the dashboard mirror stays in sync.
# Engines should prefer get_metrics() from fluxrules.core.metrics instead of
# calling these directly.


def increment_events_processed() -> None:
    """Increment events-processed (legacy shim - prefer ``get_metrics()``)."""
    if _events_processed is not None:
        _events_processed.labels(engine="PHREAK").inc()
    _dashboard_stats["events_processed"] += 1


def increment_rules_fired(count: int = 1) -> None:
    """Increment rules-fired (legacy shim - prefer ``get_metrics()``)."""
    if _rules_fired is not None:
        _rules_fired.labels(engine="PHREAK").inc(count)
    _dashboard_stats["rules_fired"] += count


def observe_processing_time(duration_seconds: float) -> None:
    """Observe processing time (legacy shim - prefer ``get_metrics()``)."""
    if _processing_time is not None:
        _processing_time.labels(engine="PHREAK").observe(duration_seconds)
    _dashboard_stats["total_processing_time_ms"] += duration_seconds * 1000
    _dashboard_stats["evaluation_count"] += 1


def increment_comparison_metric(metric_name: str, count: int = 1) -> None:
    """Increment a comparison edge-case counter (legacy shim).

    Args:
        metric_name: The stat bucket name.
        count: Amount to increment by.
    """
    if _comparison_events is not None:
        for _ in range(count):
            _comparison_events.labels(kind=metric_name).inc()
    if metric_name in _dashboard_stats:
        _dashboard_stats[metric_name] += count


def get_dashboard_metrics() -> dict:
    """Return a JSON-serialisable snapshot for the dashboard endpoint.

    Returns:
        Dict with aggregated counters and average processing time.
    """
    avg_time = 0.0
    if _dashboard_stats["evaluation_count"] > 0:
        avg_time = (
            _dashboard_stats["total_processing_time_ms"] / _dashboard_stats["evaluation_count"]
        )

    return {
        "events_processed": _dashboard_stats["events_processed"],
        "rules_fired": _dashboard_stats["rules_fired"],
        "avg_processing_time_ms": round(avg_time, 2),
        "total_evaluations": _dashboard_stats["evaluation_count"],
        "strict_comparison": {
            "type_mismatch": _dashboard_stats["comparison_type_mismatch"],
            "string_bool_coercions": _dashboard_stats["string_bool_coercions"],
            "null_evaluations": _dashboard_stats["strict_null_evaluations"],
        },
    }
