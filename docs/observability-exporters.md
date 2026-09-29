# External Observability Exporters

The FactPipeline framework provides out-of-the-box support for integrating with popular
observability backends via the **extensible `ObservabilityHook` protocol**. This page
documents the built-in exporters for **Prometheus** and **OpenTelemetry**.

## Architecture

The observability system is built on the `ObservabilityHook` protocol - a minimal,
Python protocol that any class can implement to receive pipeline events. This design
ensures:

- **No coupling** between core pipeline logic and external backends
- **Graceful degradation** if a backend is misconfigured or unavailable
- **Easy extension** for custom backends (datadog, newrelic, etc.)

```python
# The protocol (from fluxrules.pipeline.observability)
from typing import Protocol

from fluxrules.pipeline import Transform


class ObservabilityHook(Protocol):
    def on_pipeline_start(self, pipeline_name: str, fact: dict) -> None: ...
    def on_transform_start(self, transform: Transform, fact: dict) -> None: ...
    def on_transform_end(self, transform: Transform, fact: dict, duration: float) -> None: ...
    def on_transform_error(self, transform: Transform, fact: dict, error: Exception) -> None: ...
    def on_pipeline_end(self, pipeline_name: str, fact: dict, duration: float) -> None: ...
    def on_pipeline_error(self, pipeline_name: str, fact: dict, error: Exception) -> None: ...
```

Both `PrometheusHook` and `OpenTelemetryHook` implement this protocol. They are **optional
dependencies** - use only what you need.

---

## Prometheus Exporter

Export metrics to **Prometheus** for time-series monitoring and alerting.

### Installation

```bash
pip install prometheus_client
```

### Quick Start

```python
# python skip
from fluxrules.pipeline import FactPipeline, Flatten
from fluxrules.pipeline import PrometheusHook

# Create the exporter
prometheus_hook = PrometheusHook(namespace="myapp", subsystem="pipeline")

# Attach to pipeline
pipeline = FactPipeline([Flatten()], hooks=[prometheus_hook], name="normalize_facts")

# Use the pipeline - metrics are automatically recorded
fact = pipeline({"user": {"id": "u_1"}})

# Expose metrics (standard approach)
from prometheus_client import start_http_server

start_http_server(0)  # Use an available port; production deployments may choose a fixed port.
```

### Metrics Exported

The `PrometheusHook` registers the following metrics in the global Prometheus registry:

| Metric | Type | Labels | Description |
|--------|------|--------|-------------|
| `myapp_pipeline_pipeline_runs_total` | Counter | `pipeline_name` | Total pipeline executions |
| `myapp_pipeline_pipeline_errors_total` | Counter | `pipeline_name` | Total pipeline failures |
| `myapp_pipeline_pipeline_duration_seconds` | Histogram | `pipeline_name` | Pipeline execution duration |
| `myapp_pipeline_transform_invocations_total` | Counter | `transform_name` | Transform invocation count |
| `myapp_pipeline_transform_errors_total` | Counter | `transform_name` | Transform error count |
| `myapp_pipeline_transform_duration_seconds` | Histogram | `transform_name` | Transform execution duration |

The histogram buckets are optimized for typical fact-processing latencies:
- Pipelines: `[0.001s, 0.01s, 0.05s, 0.1s, 0.5s, 1.0s, 5.0s]`
- Transforms: `[0.001s, 0.01s, 0.05s, 0.1s, 0.5s, 1.0s]`

### Example: Querying with Prometheus

```promql
# Pipeline success rate
rate(myapp_pipeline_pipeline_runs_total[1m]) / rate(myapp_pipeline_pipeline_errors_total[1m])

# Average pipeline latency
histogram_quantile(0.99, rate(myapp_pipeline_pipeline_duration_seconds_bucket[1m]))

# Transform-level insights
topk(5, rate(myapp_pipeline_transform_invocations_total[1m]))
```

### Metric Caching & Custom Registries

Prometheus forbids registering two collectors with the same name in one registry.
`PrometheusHook` handles this by **caching collectors per `(registry, namespace, subsystem)`**,
so constructing the hook repeatedly is safe and never raises a
`Duplicated timeseries in CollectorRegistry` error:

```python
hook1 = PrometheusHook(namespace="myapp")
hook2 = PrometheusHook(namespace="myapp")  # Reuses the same cached collectors
assert hook1._pipeline_runs_total is hook2._pipeline_runs_total
```

By default metrics are registered in the global `prometheus_client.REGISTRY`. For
**test isolation** or **multi-tenant** setups, pass your own `CollectorRegistry`:

```python
from prometheus_client import CollectorRegistry

registry = CollectorRegistry()
hook = PrometheusHook(namespace="tenant_a", registry=registry)
# Metrics for tenant_a are isolated from the global registry.
```

---

## OpenTelemetry Exporter

Export traces and metrics to **OpenTelemetry** for distributed tracing, correlation, and
context propagation.

### Installation

```bash
# Core OpenTelemetry API + SDK
pip install opentelemetry-api opentelemetry-sdk

# Add an exporter (choose one or more)
pip install opentelemetry-exporter-otlp          # OTLP - Jaeger, Tempo, Collector, etc.
pip install opentelemetry-exporter-zipkin        # Zipkin
```

> **Tip:** Modern Jaeger ingests OTLP natively, so the OTLP exporter is the
> recommended path. The standalone `opentelemetry-exporter-jaeger` package is
> deprecated and removed in recent OpenTelemetry releases.

### Quick Start

```python
from fluxrules.pipeline import FactPipeline, Flatten
from fluxrules.pipeline import OpenTelemetryHook

# Create the exporter
otel_hook = OpenTelemetryHook(service_name="my_rule_engine", version="1.0.0")

# Attach to pipeline
pipeline = FactPipeline([Flatten()], hooks=[otel_hook], name="normalize_facts")

# Use the pipeline - traces are automatically recorded
fact = pipeline({"user": {"id": "u_1"}})

# Traces appear in your configured OpenTelemetry backend
# (Jaeger, Tempo, DataDog, New Relic, etc.)
```

### Span Structure

The `OpenTelemetryHook` creates a single parent span per pipeline execution, recording
transform events as child events within that span:

```
Span: pipeline.normalize_facts
  ├─ Event: transform.start (Flatten)
  ├─ Event: transform.end (Flatten, duration: 0.0012s)
  ├─ Event: transform.start (Rename)
  ├─ Event: transform.end (Rename, duration: 0.0008s)
  ├─ Status: OK
  └─ Attributes:
      pipeline.name: normalize_facts
      pipeline.duration_seconds: 0.0021
      fact.keys: ["user", "order"]
```

The span is created with `tracer.start_span(...)` (not `start_as_current_span`) because
the hook holds a single span across several discrete callbacks rather than within one
`with` block. Success and failure are reported through the **native span status**
(`StatusCode.OK` / `StatusCode.ERROR`), and failures additionally call
`span.record_exception(error)` - the idiomatic OpenTelemetry way to attach an exception,
which your backend renders as an `exception` event with stack trace.

### Span Attributes

Each pipeline span includes:

| Attribute | Type | Example |
|-----------|------|---------|
| `pipeline.name` | string | `"normalize_facts"` |
| `pipeline.duration_seconds` | float | `0.0021` |
| `fact.keys` | list[str] | `["user", "order"]` |

The span **status** conveys success/failure:

| Outcome | Span status | Extra |
|---------|-------------|-------|
| success | `StatusCode.OK` | - |
| error | `StatusCode.ERROR` (description = error message) | `record_exception(error)` emits an `exception` event |

Transform events include:

| Event | Attributes |
|-------|------------|
| `transform.start` | `transform.name`, `transform.version` |
| `transform.end` | `transform.name`, `duration_seconds` |
| `transform.error` | `transform.name`, `error.type`, `error.message` |

### Example: Exporting via OTLP (Jaeger, Tempo, Collector)

```python
# python skip
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter

# Configure the OTLP exporter (points at a Collector / Jaeger / Tempo OTLP endpoint)
otlp_exporter = OTLPSpanExporter(endpoint="http://localhost:4317", insecure=True)

trace_provider = TracerProvider()
trace_provider.add_span_processor(BatchSpanProcessor(otlp_exporter))

# Set as the global provider BEFORE constructing the hook so it picks up this tracer
trace.set_tracer_provider(trace_provider)

# Now create your pipeline
from fluxrules.pipeline import FactPipeline, Flatten, OpenTelemetryHook

hook = OpenTelemetryHook(service_name="my_app")
pipeline = FactPipeline([Flatten()], hooks=[hook])
pipeline({"user": {"id": "u_1"}})

# Spans automatically appear in your backend (Jaeger/Tempo UI, etc.)
```

> **Testing tip:** For unit tests, swap the OTLP exporter for the SDK's
> `InMemorySpanExporter` and assert on `exporter.get_finished_spans()` - exactly
> how `tests/unit/pipeline/test_exporters.py` validates this hook end-to-end.

### Error Handling

The `OpenTelemetryHook` degrades gracefully if OpenTelemetry is misconfigured:

```python
# python skip
# If the tracer is not properly initialized, the hook
# swallows exceptions and continues silently
hook = OpenTelemetryHook()
pipeline = FactPipeline([...], hooks=[hook])

# Even if OTEL is broken, your pipeline runs normally
pipeline({"data": "here"})  # Works fine
```

---

## Combining Exporters

Use **multiple exporters simultaneously** to send metrics and traces to different backends:

```python
from fluxrules.pipeline import (
    FactPipeline,
    Flatten,
    MetricsHook,
    PipelineMetrics,
    PrometheusHook,
    OpenTelemetryHook,
)

# Create exporters
metrics_obj = PipelineMetrics()
hooks = [
    MetricsHook(metrics_obj),  # In-memory metrics
    PrometheusHook(),  # Prometheus metrics
    OpenTelemetryHook(),  # Distributed tracing
]

# Single pipeline, multiple backends
pipeline = FactPipeline([Flatten()], hooks=hooks, name="multi_backend")

# All three backends receive events simultaneously
pipeline({"user": {"id": "u_1"}})

# Query metrics locally
print(metrics_obj.as_dict())

# Prometheus: http://localhost:8000/metrics
# OpenTelemetry: Check your Jaeger/Tempo/etc.
```

---

## Building Custom Exporters

The `ObservabilityHook` protocol makes it easy to build custom exporters. Example:
exporting to **Datadog**:

```python
from fluxrules.pipeline.observability import ObservabilityHook
from fluxrules.pipeline.base import Transform
from typing import Any


class DatadogHook:
    """Send pipeline events to Datadog."""

    def __init__(self, api_key: str):
        self.api_key = api_key
        # Initialize Datadog client

    def on_transform_end(self, transform: Transform, fact: dict[str, Any], duration: float) -> None:
        """Send transform completion metric to Datadog."""
        datadog_client.metric(
            f"pipeline.transform.duration", duration, tags=[f"transform:{transform.metadata.name}"]
        )

    # ... implement other protocol methods
```

Then use it:

```python
hook = DatadogHook(api_key="...")
pipeline = FactPipeline([...], hooks=[hook])
```

---

## Best Practices

### 1. **Use Namespacing**

Avoid metric collisions in Prometheus by using a unique namespace:

```python
# Good: namespaced by service
PrometheusHook(namespace="user_service", subsystem="pipeline")

# Good: namespaced by environment
PrometheusHook(namespace="prod_ml_engine", subsystem="pipeline")
```

### 2. **Combine Local + Remote Metrics**

Track local metrics for debugging + remote metrics for production monitoring:

```python
metrics = PipelineMetrics()  # Local, in-memory
hooks = [
    MetricsHook(metrics),
    PrometheusHook(),  # Production monitoring
]

pipeline = FactPipeline([...], hooks=hooks)
```

### 3. **Instrument with Custom Transforms**

Combine exporters with custom transforms to add business logic instrumentation:

```python
from fluxrules.pipeline import FactPipeline, Transform


class BusinessLogicTransform(Transform):
    """Track domain-specific events (e.g., fraud flags)."""

    def __call__(self, fact):
        if fact.get("fraud_score", 0) > 0.8:
            print(f"HIGH RISK: {fact['user_id']}")  # Or emit custom metric
        return fact
```

### 4. **Monitor Error Rates**

Use Prometheus queries to monitor transform-level error rates:

```promql
# Transform error rate
rate(myapp_pipeline_transform_errors_total[1m]) 
  / ignoring(instance) rate(myapp_pipeline_transform_invocations_total[1m])
```

---

## Performance Considerations

- **Prometheus**: Minimal overhead; metrics are incremented atomically.
- **OpenTelemetry**: Span creation has measurable overhead (~microseconds per event);
  use sampled tracing in high-throughput scenarios.

To reduce overhead in production, consider:

```python
# python skip
# Only use OpenTelemetry if tracing is enabled
hooks = [MetricsHook()]
if TRACING_ENABLED:
    hooks.append(OpenTelemetryHook())

pipeline = FactPipeline([...], hooks=hooks)
```

---

## Troubleshooting

### Prometheus metrics not appearing

- Ensure `prometheus_client` is installed: `pip install prometheus_client`
- Call `start_http_server(port)` to expose metrics
- Check `http://localhost:PORT/metrics`

### OpenTelemetry spans not appearing

- Ensure OpenTelemetry SDK and exporter are installed
- Configure a global `TracerProvider` **before** creating the hook
- Check that your exporter backend (Jaeger, Tempo, etc.) is running

### Import errors

Both exporters are optional. If you see `ImportError`, install the required library:

```bash
pip install prometheus_client opentelemetry-api opentelemetry-sdk
```
