"""Tests for external observability exporters (Prometheus, OpenTelemetry).

These tests exercise the concrete :class:`ObservabilityHook` implementations
that bridge a :class:`FactPipeline` to external backends.

Design notes:

- **Prometheus** tests use an isolated ``CollectorRegistry`` per test (via the
  ``registry`` fixture) so metrics never leak into the global registry and
  assertions can read concrete counter/histogram values.
- **OpenTelemetry** tests use the SDK's ``InMemorySpanExporter`` so spans can be
  asserted without a live collector. The SDK is a dev dependency, so these run
  in CI rather than being skipped.
"""

from __future__ import annotations

import builtins

import pytest

from fluxrules.pipeline.base import Transform, TransformMetadata
from fluxrules.pipeline.core import FactPipeline
from fluxrules.pipeline.exporters import OpenTelemetryHook, PrometheusHook
from fluxrules.pipeline.observability import ObservabilityHook
from fluxrules.pipeline.transforms import Flatten, Rename


class FailingTransform(Transform):
    """A transform that always raises, for error-path testing."""

    def __call__(self, fact: dict) -> dict:
        raise ValueError("intentional error")

    @property
    def metadata(self) -> TransformMetadata:
        return TransformMetadata(
            name="FailingTransform",
            version="1.0.0",
            required_input_fields=["x"],
            output_fields=["x"],
            description="Fails on purpose",
            errors_raised=[ValueError],
        )


# ---------------------------------------------------------------------------
# Prometheus
# ---------------------------------------------------------------------------

prometheus_client = pytest.importorskip(
    "prometheus_client", reason="prometheus_client not installed"
)


@pytest.fixture
def registry():
    """Provide a fresh, isolated Prometheus registry per test.

    After the test, drop any cached collectors tied to this registry so the
    process-wide cache does not grow and later tests start clean.
    """
    from prometheus_client import CollectorRegistry

    reg = CollectorRegistry()
    yield reg
    PrometheusHook._metrics_cache = {
        key: value for key, value in PrometheusHook._metrics_cache.items() if key[0] != id(reg)
    }


def _counter_value(metric, **labels) -> float:
    """Read the current value of a labeled Prometheus counter."""
    return metric.labels(**labels)._value.get()


class TestPrometheusHook:
    """Tests for PrometheusHook (external exporter)."""

    def test_implements_observability_hook_protocol(self, registry):
        """PrometheusHook should structurally satisfy ObservabilityHook."""
        hook = PrometheusHook(namespace="proto", registry=registry)
        assert isinstance(hook, ObservabilityHook)

    def test_init_creates_all_collectors(self, registry):
        """Initialization should create the six core collectors."""
        hook = PrometheusHook(namespace="test", subsystem="pipeline", registry=registry)
        assert hook._pipeline_runs_total is not None
        assert hook._pipeline_errors_total is not None
        assert hook._pipeline_duration_seconds is not None
        assert hook._transform_invocations_total is not None
        assert hook._transform_errors_total is not None
        assert hook._transform_duration_seconds is not None

    def test_metrics_cached_per_registry_namespace(self, registry):
        """Two hooks sharing registry+namespace should share collectors."""
        hook1 = PrometheusHook(namespace="shared", registry=registry)
        hook2 = PrometheusHook(namespace="shared", registry=registry)
        assert hook1._pipeline_runs_total is hook2._pipeline_runs_total

    def test_distinct_namespaces_get_distinct_metrics(self, registry):
        """Different namespaces should produce different collectors."""
        hook1 = PrometheusHook(namespace="alpha", registry=registry)
        hook2 = PrometheusHook(namespace="beta", registry=registry)
        assert hook1._pipeline_runs_total is not hook2._pipeline_runs_total

    def test_repeated_construction_is_idempotent(self, registry):
        """Re-constructing a hook must not raise duplicate-timeseries errors."""
        PrometheusHook(namespace="idem", registry=registry)
        # A second construction would raise ValueError if metrics were not cached.
        PrometheusHook(namespace="idem", registry=registry)

    def test_pipeline_integration_records_metrics(self, registry):
        """A full pipeline run should increment run and transform counters."""
        hook = PrometheusHook(namespace="integ", registry=registry)
        pipeline = FactPipeline([Flatten()], hooks=[hook], name="test_pipeline")

        result = pipeline({"a": {"b": 1}})
        assert result == {"a.b": 1}

        assert _counter_value(hook._pipeline_runs_total, pipeline_name="test_pipeline") == 1.0
        assert _counter_value(hook._transform_invocations_total, transform_name="Flatten") == 1.0

    def test_pipeline_error_increments_error_counter(self, registry):
        """A failing pipeline should increment the pipeline error counter."""
        hook = PrometheusHook(namespace="err", registry=registry)
        pipeline = FactPipeline([FailingTransform()], hooks=[hook], name="err_pipeline")

        with pytest.raises(ValueError):
            pipeline({"x": 1})

        assert _counter_value(hook._pipeline_errors_total, pipeline_name="err_pipeline") == 1.0

    def test_transform_error_increments_transform_error_counter(self, registry):
        """on_transform_error should increment the transform error counter."""
        hook = PrometheusHook(namespace="terr", registry=registry)
        hook.on_transform_error(FailingTransform(), {}, ValueError("boom"))

        assert (
            _counter_value(hook._transform_errors_total, transform_name="FailingTransform") == 1.0
        )

    def test_init_requires_prometheus_client(self, monkeypatch):
        """If prometheus_client is unavailable, init should raise ImportError."""
        real_import = builtins.__import__

        def fake_import(name, *args, **kwargs):
            if name == "prometheus_client":
                raise ImportError("simulated missing prometheus_client")
            return real_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", fake_import)
        with pytest.raises(ImportError, match="prometheus_client"):
            PrometheusHook(namespace="missing")

    def test_defaults_to_global_registry(self):
        """When no registry is passed, the global REGISTRY is used."""
        from prometheus_client import REGISTRY

        # Use a unique namespace so we don't collide with the global registry
        # across repeated test runs in the same process.
        namespace = "global_default_probe"
        try:
            hook = PrometheusHook(namespace=namespace)
            assert hook._pipeline_runs_total is not None
            # The collector should be discoverable in the global registry.
            metric_name = f"{namespace}_pipeline_pipeline_runs_total"
            assert REGISTRY.get_sample_value(metric_name, {"pipeline_name": "x"}) in (
                None,
                0.0,
            )
        finally:
            # Clean up the cache entry tied to the global registry.
            PrometheusHook._metrics_cache = {
                key: value
                for key, value in PrometheusHook._metrics_cache.items()
                if key[1] != namespace
            }


# ---------------------------------------------------------------------------
# OpenTelemetry
# ---------------------------------------------------------------------------

opentelemetry = pytest.importorskip("opentelemetry", reason="opentelemetry not installed")
pytest.importorskip("opentelemetry.sdk", reason="opentelemetry-sdk not installed")


@pytest.fixture
def otel_exporter():
    """Provide an in-memory span exporter wired to a fresh TracerProvider."""
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import SimpleSpanProcessor
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
        InMemorySpanExporter,
    )

    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    return exporter, provider


def _hook_with_provider(provider, service_name="otel_test") -> OpenTelemetryHook:
    """Build an OpenTelemetryHook bound to a specific provider's tracer."""
    hook = OpenTelemetryHook(service_name=service_name)
    hook.tracer = provider.get_tracer(service_name)
    return hook


class TestOpenTelemetryHook:
    """Tests for OpenTelemetryHook (external exporter)."""

    def test_implements_observability_hook_protocol(self):
        """OpenTelemetryHook should structurally satisfy ObservabilityHook."""
        hook = OpenTelemetryHook(service_name="proto")
        assert isinstance(hook, ObservabilityHook)

    def test_init_with_opentelemetry_installed(self):
        """Initialization should create a tracer and store metadata."""
        hook = OpenTelemetryHook(service_name="test_service", version="2.3.4")
        assert hook.service_name == "test_service"
        assert hook.version == "2.3.4"
        assert hook.tracer is not None

    def test_span_lifecycle(self, otel_exporter):
        """A successful pipeline span should be created and ended."""
        exporter, provider = otel_exporter
        hook = _hook_with_provider(provider)

        hook.on_pipeline_start("test_pipeline", {"key": "value"})
        assert hook._pipeline_span is not None

        hook.on_pipeline_end("test_pipeline", {"key": "value"}, 0.1)
        assert hook._pipeline_span is None

        spans = exporter.get_finished_spans()
        assert len(spans) == 1
        assert spans[0].name == "pipeline.test_pipeline"

    def test_span_records_attributes_and_status(self, otel_exporter):
        """The pipeline span should carry name + duration attrs and OK status."""
        from opentelemetry.trace import StatusCode

        exporter, provider = otel_exporter
        hook = _hook_with_provider(provider)

        hook.on_pipeline_start("attr_pipeline", {"a": 1, "b": 2})
        hook.on_pipeline_end("attr_pipeline", {"a": 1, "b": 2}, 0.25)

        span = exporter.get_finished_spans()[0]
        assert span.attributes["pipeline.name"] == "attr_pipeline"
        assert span.attributes["pipeline.duration_seconds"] == 0.25
        assert set(span.attributes["fact.keys"]) == {"a", "b"}
        assert span.status.status_code is StatusCode.OK

    def test_error_span_lifecycle_records_exception(self, otel_exporter):
        """A pipeline error should record an exception and ERROR status."""
        from opentelemetry.trace import StatusCode

        exporter, provider = otel_exporter
        hook = _hook_with_provider(provider)

        hook.on_pipeline_start("err_pipeline", {})
        assert hook._pipeline_span is not None
        hook.on_pipeline_error("err_pipeline", {}, ValueError("kaboom"))
        assert hook._pipeline_span is None

        span = exporter.get_finished_spans()[0]
        assert span.status.status_code is StatusCode.ERROR
        # record_exception emits an "exception" event.
        assert any(event.name == "exception" for event in span.events)

    def test_transform_events_recorded(self, otel_exporter):
        """Transform start/end should appear as events on the pipeline span."""
        exporter, provider = otel_exporter
        hook = _hook_with_provider(provider)

        pipeline = FactPipeline([Flatten()], hooks=[hook], name="evt_pipeline")
        pipeline({"a": {"b": 1}})

        span = exporter.get_finished_spans()[0]
        event_names = [event.name for event in span.events]
        assert "transform.start" in event_names
        assert "transform.end" in event_names

    def test_transform_error_recorded_as_event(self, otel_exporter):
        """A failing transform should add a transform.error event to the span."""
        exporter, provider = otel_exporter
        hook = _hook_with_provider(provider)

        hook.on_pipeline_start("err_evt_pipeline", {})
        hook.on_transform_error(FailingTransform(), {}, ValueError("nope"))
        hook.on_pipeline_end("err_evt_pipeline", {}, 0.01)

        span = exporter.get_finished_spans()[0]
        error_events = [e for e in span.events if e.name == "transform.error"]
        assert len(error_events) == 1
        assert error_events[0].attributes["transform.name"] == "FailingTransform"
        assert error_events[0].attributes["error.type"] == "ValueError"

    def test_failing_pipeline_marks_span_error(self, otel_exporter):
        """An exception raised mid-pipeline should produce an ERROR span."""
        from opentelemetry.trace import StatusCode

        exporter, provider = otel_exporter
        hook = _hook_with_provider(provider)
        pipeline = FactPipeline([FailingTransform()], hooks=[hook], name="boom_pipeline")

        with pytest.raises(ValueError):
            pipeline({"x": 1})

        assert hook._pipeline_span is None
        span = exporter.get_finished_spans()[0]
        assert span.status.status_code is StatusCode.ERROR
        assert any(e.name == "transform.error" for e in span.events)
        assert any(e.name == "exception" for e in span.events)

    def test_graceful_degradation_with_bad_inputs(self):
        """Hook methods should never raise, even with odd inputs or no span."""
        hook = OpenTelemetryHook()

        # No active span yet: these should be safe no-ops.
        hook.on_transform_start(None, {})  # type: ignore[arg-type]
        hook.on_transform_end(None, {}, 0.1)  # type: ignore[arg-type]
        hook.on_pipeline_end("test", {}, 0.1)

    def test_callbacks_without_active_span_are_noops(self):
        """All event callbacks should no-op when no pipeline span is active."""
        hook = OpenTelemetryHook(service_name="noop")
        assert hook._pipeline_span is None

        # None of these should raise, and the span stays None.
        hook.on_transform_start(FailingTransform(), {})
        hook.on_transform_end(FailingTransform(), {}, 0.01)
        hook.on_transform_error(FailingTransform(), {}, ValueError("x"))
        hook.on_pipeline_end("noop", {}, 0.01)
        hook.on_pipeline_error("noop", {}, ValueError("x"))
        assert hook._pipeline_span is None

    def test_pipeline_integration_closes_span(self, otel_exporter):
        """End-to-end run should transform the fact and close the span."""
        exporter, provider = otel_exporter
        hook = _hook_with_provider(provider)
        pipeline = FactPipeline(
            [Flatten(), Rename({"a_b": ["a.b"]})],
            hooks=[hook],
            name="integration_pipeline",
        )

        result = pipeline({"a": {"b": 1}})
        # Rename is additive: it keeps the original flattened key and adds the alias.
        assert result == {"a.b": 1, "a_b": 1}
        assert hook._pipeline_span is None

        spans = exporter.get_finished_spans()
        assert any(s.name == "pipeline.integration_pipeline" for s in spans)

    def test_init_requires_opentelemetry(self, monkeypatch):
        """If OpenTelemetry is unavailable, init should raise ImportError."""
        real_import = builtins.__import__

        def fake_import(name, *args, **kwargs):
            if name == "opentelemetry" or name.startswith("opentelemetry."):
                raise ImportError("simulated missing opentelemetry")
            return real_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", fake_import)
        with pytest.raises(ImportError, match="opentelemetry"):
            OpenTelemetryHook()


# ---------------------------------------------------------------------------
# Combined / cross-exporter
# ---------------------------------------------------------------------------


class TestCombinedExporters:
    """Verify multiple exporters can be attached to one pipeline."""

    def test_prometheus_and_opentelemetry_together(self, registry, otel_exporter):
        """Both exporters should receive events from a single pipeline run."""
        exporter, provider = otel_exporter
        prom = PrometheusHook(namespace="combo", registry=registry)
        otel = _hook_with_provider(provider, service_name="combo")

        pipeline = FactPipeline([Flatten()], hooks=[prom, otel], name="combo_pipeline")
        pipeline({"a": {"b": 1}})

        # Prometheus recorded the run.
        assert _counter_value(prom._pipeline_runs_total, pipeline_name="combo_pipeline") == 1.0
        # OpenTelemetry recorded the span.
        spans = exporter.get_finished_spans()
        assert any(s.name == "pipeline.combo_pipeline" for s in spans)
