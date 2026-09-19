# Observability

**Prerequisites:** [Deployment](deployment.md).

---

Monitor FluxRules with engine metrics, pipeline hooks, logs, and optional
Prometheus/OpenTelemetry exporters. Exporters are opt-in; the core engine does
not start a metrics server or emit external telemetry by default.

## PHREAK engine metrics

Enable the bounded in-process collector when you need candidate, selectivity,
latency, or streaming-cache signals:

```python
from fluxrules import Rule
from fluxrules.engine.phreak import PhreakEngine

rule = Rule(
    name="amount_check",
    condition_dsl={"type": "condition", "field": "amount", "op": ">", "value": 100},
    action="review",
    persist=False,
)
engine = PhreakEngine(enable_metrics=True)
engine.load_rules([rule])
engine.evaluate({"amount": 150})

metrics = engine.get_observability_metrics()
print(metrics["alpha_prune_ratio"])
print(metrics["eval_latency_ms_p95"])
```

The collector is bounded and advisory. Useful operational signals include
`candidates_per_fact_out`, `alpha_prune_ratio`, `eval_latency_ms_p95`,
`linked_rules_avg`, `node_memory.hit_rate` in streaming mode, and
`working_memory_size`.

## Metrics (Prometheus)

Prometheus export is optional and is attached to a `FactPipeline` through a
`PrometheusHook`:

```python
from fluxrules.pipeline import FactPipeline, Flatten
from fluxrules.pipeline.exporters import PrometheusHook

hook = PrometheusHook(namespace="fluxrules")
pipeline = FactPipeline([Flatten()], hooks=[hook])
pipeline({"user": {"id": "u1"}})
```

The hook exposes pipeline and transform metrics such as pipeline run/error
counters, pipeline duration, transform invocation/error counters, and transform
duration histograms.

The hook records pipeline and transform counters/histograms in the registry
provided to it. A `/metrics` HTTP endpoint requires an application-owned
Prometheus exposition route; the core pipeline does not start one automatically.

```bash
# The host application exposes its configured Prometheus registry.
curl http://localhost:8000/metrics
```

## Logging

Logs are output to stdout (structured for container environments):

```bash
# Set log level
export FLUXRULES_LOG_LEVEL=INFO

# Redirect to logging backend
docker run -v /var/log/fluxrules:/app/logs fluxrules:latest
```

## Distributed tracing (OpenTelemetry)

If extras include `[otel]`, attach `OpenTelemetryHook` to a pipeline and configure
the exporter/provider in the host application:

```bash
# Enable OpenTelemetry
export OTEL_EXPORTER_OTLP_ENDPOINT=http://otel-collector:4317
export OTEL_EXPORTER_OTLP_PROTOCOL=grpc
export OTEL_SERVICE_NAME=fluxrules
```

```python
from fluxrules.pipeline import FactPipeline, Flatten
from fluxrules.pipeline.exporters import OpenTelemetryHook

hook = OpenTelemetryHook(service_name="fluxrules")
pipeline = FactPipeline([Flatten()], hooks=[hook])
pipeline({"user": {"id": "u1"}})
```

## Health checks

Liveness/readiness endpoint:

```bash
GET /health
```

Response:
```json
{
  "status": "healthy",
  "version": "0.0.1"
}
```

---

## Next Steps

- **Troubleshooting** — See [Troubleshooting](troubleshooting.md) for common issues
- **Deployment** — See [Deployment](deployment.md) for production setup
