# Benchmarks

**Prerequisites:** [The FluxRules Engine](engine-comparison.md).

---

Performance characteristics of the FluxRules PHREAK engine.

## Evidence boundary

The repository has two benchmark categories:

1. **Pure matcher evidence** - `tests/performance/test_scale_readiness.py`
	directly evaluated 1,000,000 generated facts against 1,200 generated rules
	on commit `a572be9` using CPython 3.11.13 on macOS arm64. It compared 2,000
	complete fired-rule sets against `ReferenceEvaluator`, measured 428.82
	facts/s and 140.70 MB peak RSS, and passed the 150 facts/s and 2,048 MB
	thresholds. The retained artifact is
	`.research/scale-readiness-2026-09-16.json`.
2. **Boundary evidence** - actions, persistence, HTTP serialization, auth,
	queueing, process concurrency, and sticky streaming are separate costs and
	contracts. They are not included in the pure matcher result above.

Do not interpret the pure matcher measurement as end-to-end service throughput.
The next benchmark set should use the same deterministic rule/fact profiles and
report exact result parity, p50/p95/p99 latency, throughput, peak RSS, and
failure counts for each boundary independently.

## Test environment

- Python 3.11
- Single-threaded evaluation
- Test dataset: cross_border_payment_risk_triage (shared dataset, 3 facts)
- Rules: 10-1000 typical rules

## Latency (per evaluation)

| Rule Count | PHREAK |
|------------|--------|
| 10 rules | ~0.5ms |
| 100 rules | ~2ms |
| 500 rules | ~10ms |
| 1000 rules | ~20ms |

**Notes:**
- Latency grows roughly linearly with rule count
- Latency measured in `EvaluationResult.latency_ms`

## Memory usage

| Rule Count | PHREAK |
|------------|--------|
| 10 rules | ~1MB |
| 100 rules | ~1MB |
| 1000 rules | ~2MB |

**Notes:**
- Constant footprint - rules are loaded once and facts evaluate independently

## Startup time

| Rule Count | Time |
|------------|------|
| 10 rules | ~1ms |
| 100 rules | ~1ms |
| 1000 rules | ~2ms |

**Note:** `load_rules()` cost is small; most work happens at `evaluate()` time.

## Throughput

Single-threaded with batch evaluation:

- **PHREAK:** ~2000 evaluations/sec (500 rules, simple conditions)

**Note:** Actual throughput depends on rule complexity and condition logic.

## Required follow-up profiles

Before making broader capacity claims, run and retain separate results for:

- selective, dense/hot-field, nested, and high-match rule distributions;
- deterministic no-op action execution and action failure handling;
- persistence/load phases with result parity after reload;
- in-process HTTP and a real local server path with JSON/error timing;
- bounded queue producer/consumer behavior and backpressure;
- one, two, and four process workers with ordered result parity;
- sticky streaming shards with repeated/changed facts and memory growth.

Each profile must identify whether it measures matcher-only or end-to-end work.

---

## Next Steps

- **The FluxRules Engine** - See [The FluxRules Engine](engine-comparison.md)
- **Deployment** - See [Deployment](deployment.md) for scaling
