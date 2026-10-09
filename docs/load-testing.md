# FluxRules Load Testing & Scalability Analysis

This document addresses production scalability concerns: **Can PHREAK handle millions of facts daily with 50K+ rules?**

> **How to read these numbers.** Throughput and daily-capacity figures below come
> from the **realistic-rule benchmark** (`tests/performance/perf_realistic_rules.py`),
> measured on a **pre-loaded** engine (the per-request reload defect was fixed in
> the P0 trust work - the engine is built once and hot-swapped, never rebuilt per
> fact). They are **measured, not extrapolated** from idealized batch throughput.
> Your numbers depend on your rules' selectivity - **measure your real set** with
> the harness before sizing.

---

## Executive Summary

**Short answer:** Yes for millions/day; the path to tens-to-hundreds of millions
is **horizontal** (more processes/pods), not a single magic thread.

- **Single process:** A pre-loaded PHREAK engine evaluates one fact against the
 surviving candidate rules. Per-fact cost scales with **surviving candidates**,
 which the always-on alpha pre-filter minimizes on realistic (selective) rules.
- **Throughput (measured, realistic mixed rules):** order **10²-10³ facts/sec
 per process** at 10K-100K rules, depending on selectivity. Run the harness for
 your set: `python tests/performance/perf_realistic_rules.py`.
- **Daily volume (one process):** reported as **measured sustained throughput ×
 86,400 s** with the method stated - typically **single-digit to low-tens of
 millions/day** per process on realistic rules. (No "billions/day single-thread"
 claim - that was idealized batch math and has been removed.)
- **For tens-to-hundreds of millions daily:** deploy N processes/pods behind a
 queue (Kafka, Redis Streams) with sticky routing for any streaming state.
- **Honest worst case:** if most rules test **one low-selectivity field that
 every fact carries**, the alpha filter cannot prune and per-fact cost is
 **O(rules)**. Measure this case (`--adversarial`) and size for it if your rules
 look like that.

---

## Benchmark Data

### Realistic-rule benchmark (the honest path)

Run: `python tests/performance/perf_realistic_rules.py [--rules N ...] [--adversarial] [--parallel]`

This harness generates rule sets with **mixed fields, ranges, `in`-sets, `==`,
and AND/OR depth** at a configurable match rate, then reports **per-fact p50 /
p95 / p99**, candidates/fact before and after the alpha layer, the cumulative
**alpha prune ratio**, throughput, and an honest daily-capacity projection. A
**process-pool** run (`--parallel`) reports multi-core scaling, and
`--adversarial` measures the low-selectivity hot-field worst case.

A CI smoke subset (`tests/engine/test_realistic_rules_smoke.py`) gates a **p95
budget** on every regular CI run so scaling regressions fail the build.

> Record your own measured table here from a pinned machine (median of N runs):
>
> | Scale | p50 / p95 / p99 (ms/fact) | Throughput (facts/s) | Alpha prune | Daily / process |
> |------:|:--------------------------|:---------------------|:------------|:----------------|
> | 10K | _measure_ | _measure_ | _measure_ | _measure_ |
> | 50K | _measure_ | _measure_ | _measure_ | _measure_ |
> | 100K | _measure_ | _measure_ | _measure_ | _measure_ |

### Committed readiness run (million-fact + horizontal scaling)

A pinned, machine-stamped result is committed at
`benchmarks/readiness_2026-09-11.json` (regenerate with
`python tests/performance/perf_realistic_rules.py --readiness --readiness-rules 1000
--readiness-facts 1000000 --parity-facts 100000 --parallel-facts 400000 --workers 8
--json benchmarks/<date>.json`). It streams **1,000,000 facts** through a
**pre-loaded 1,000-rule** engine (memory-flat via a fact generator) and records
p50/p95/p99, throughput, peak RSS, the alpha-on-vs-off **correctness parity**
check, plus a process-pool scaling run — so the "millions/day" and "horizontal
scaling" claims are backed by a reproducible artifact, not extrapolation.

Measured on the environment stamped in the artifact
(CPython 3.11.13, arm64, 12 cores):

| Run | Result |
|-----|--------|
| Streaming — 1,000 rules × 1,000,000 facts | p50 **0.89 ms** / p95 **1.12 ms** / p99 **1.25 ms**; **1,107 facts/s**; peak RSS **77.2 MiB** |
| Correctness parity (alpha on vs off) | **0 mismatches / 100,000 facts** |
| Horizontal scaling — 400,000 facts, 8 workers | **6.39× speedup**, 889 facts/s/core, fired-facts parity **OK** (400,000 == 400,000) |

The alpha layer pruned **84.1%** of candidates on this selective set. These are
this machine's numbers; regenerate on your target hardware before sizing.

### Legacy micro-benchmark (PHREAK vs reference evaluator)

Run: `pytest tests/performance/test_benchmark.py -v -s`

| Scenario | Rules | Facts per Eval | Reference | **PHREAK** |
|----------|-------|-----------------|------------|-----------|
| Micro | 10 | 5 | **0.004 ms** | **0.003 ms** |
| Small | 100 | 20 | **0.028 ms** | **0.063 ms** |
| Medium | 1,000 | 50 | **0.324 ms** | **0.598 ms** |
| Large | 10,000 | 100 | **3.391 ms** | **6.286 ms** |
| **XL** | **50,000** | **200** | 33.745 ms | **102.640 ms** |

> These use **single-field synthetic** rules (every fact carries the hot field),
> which is the *easy* case but **not** representative of production selectivity.
> Use the realistic-rule harness above for capacity planning; use this table only
> to compare PHREAK against the naive reference evaluator.

**Key insight:** PHREAK stays within a small constant factor of the naive
reference evaluator while scaling to 50K rules.

---

## Scaling Analysis

### Single-process capacity (measured, not extrapolated)

Per-fact cost is **linear in the number of surviving candidate rules**, not the
total rule count - the always-on alpha pre-filter drops rules whose necessary
conditions provably fail before any per-rule evaluation. So capacity depends on
your rules' **selectivity**, which is why we measure rather than assert a single
number.

**Methodology (§7):**

1. Build the engine **once** (production uses a versioned hot-swap holder - no
 per-request reload).
2. Warm up, then time **each** fact individually; report **p50/p95/p99**, not
 just a mean.
3. Pause GC during the timed loop so numbers reflect matcher cost.
4. Daily capacity = **measured sustained throughput × 86,400 s**, reported with
 the method stated (never idealized batch throughput × a day).

```
Single process, realistic rules:
- Measure per-fact p50/p95/p99 with perf_realistic_rules.py on your rule set.
- Daily/process  = sustained facts/sec × 86,400.
- Typical range  = single-digit to low-tens of millions/day per process,
                   driven by selectivity (alpha prune ratio).
```

> **Removed claim.** Earlier revisions stated "**2.6 billion facts/day**
> single-thread" and "**8-26 billion/day per process**." Those multiplied an
> *idealized batch* throughput by 86,400 and assumed away per-request reload,
> real selectivity, GC, and I/O. They are not defensible and have been replaced
> by the measured methodology above.

### Adversarial caveat (the honest worst case)

If most rules test **one low-selectivity field that every fact carries**, the
alpha pre-filter cannot prune - every fact reaches **O(rules)** per-rule
evaluations. The harness measures this directly:

```
python tests/performance/perf_realistic_rules.py --adversarial
```

Plan capacity for **this** number, not the selective best case, if your rule set
looks like that. (FluxRules is a high-throughput **single-fact** matcher; cross-
fact joins/temporal correlation are out of scope - see
[Engine Scope & Limits](engine-scope-and-limits.md).)

### Multi-core scaling

Python's GIL serializes CPU-bound condition evaluation within a process, so
multi-core throughput comes from **processes**, not threads. Use
`evaluate_batch_parallel` (one engine per worker process):

```
python tests/performance/perf_realistic_rules.py --parallel --workers 8
```

The harness reports parallel throughput, per-core throughput, and the speedup,
with a fired-facts parity check proving results are identical to single-process.

### Distributed architecture

For **millions of facts daily** (1-10M/day):

```
┌─────────────────────────────────────────────┐
│        Message Queue (Kafka/Redis)          │
│  (Buffer: 100K-1M facts waiting)            │
└─────────────────────────────────────────────┘
              │
              ├────────┬──────────┬──────────┐
              │        │          │          │
              ▼        ▼          ▼          ▼
         ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐
         │Instance1│ │Instance2│ │Instance3│ │Instance4│
         │PHREAK   │ │PHREAK   │ │PHREAK   │ │PHREAK   │
         │Network  │ │Network  │ │Network  │ │Network  │
         │(50K)    │ │(50K)    │ │(50K)    │ │(50K)    │
         └─────────┘ └─────────┘ └─────────┘ └─────────┘
              │        │          │          │
              └────────┴──────────┴──────────┘
                       │
                       ▼
              ┌──────────────────┐
              │  Results DB      │
              │ (PostgreSQL)     │
              └──────────────────┘
```

**Capacity (illustrative - substitute your measured per-process number):**
- N processes × (your measured facts/sec) = aggregate facts/sec
- aggregate facts/sec × 86,400 = facts/day
- Scaling is ~linear in processes for stateless evaluation; verify with
 `perf_realistic_rules.py --parallel`.

---

## PHREAK Optimizations for High Throughput

### 1. Delta Evaluation (Field-Level Dirty Tracking)

```python
# python skip
from fluxrules.engine.phreak import PhreakEngine

engine = PhreakEngine()

# Compile ruleset once
engine.load_rules(ruleset)

# Evaluate many facts with incremental updates
facts = {"customer_id": 123, "amount": 5000}
result = engine.evaluate(facts)

# Next fact: only "amount" changed
facts_updated = {"customer_id": 123, "amount": 6000}
result = engine.evaluate(facts_updated, prev_facts=facts)
# PHREAK recomputes only alphas for "amount" field ✓
```

**Impact:** 5-10× faster for incremental updates vs. full re-evaluation.

### 2. Batch Evaluation with Working Memory

```python
# python skip
# Accumulate facts in working memory (streaming_mode=True engine)
for i, fact in enumerate(facts_stream):
    engine.assert_fact(fact)
    if i % 1000 == 0:
        # Flush: evaluate the current working-memory fact set
        result = engine.evaluate(fact)
        results.append(result)
```

**Impact:** Amortizes compilation overhead, ~50K facts/batch.

### 3. Horizontal Scaling with Load Balancing

```python
# python skip
# Deploy with Docker Compose
# Each instance: 1 CPU, 1GB RAM
# Network: Redis/Kafka queue

import redis
from fastapi import FastAPI
from fluxrules.engine.phreak import PhreakEngine

app = FastAPI()
queue = redis.Redis(host="redis", port=6379)
engine = PhreakEngine()
engine.load_rules(ruleset)

@app.post("/evaluate")
def evaluate_fact(fact: dict):
    result = engine.evaluate(fact)
    queue.rpush("results", result.to_json())
    return {"status": "queued"}
```

---

## Real-World Scenarios

### Scenario 1: Fraud Detection (1M facts/day, 5K rules)

```
Daily Volume: 1,000,000 facts  (≈ 12 facts/sec average)
Rules: 5,000 (fraud detection patterns)

Setup:
- 1 process is ample: 1M/day ≈ 12 facts/sec average; even the adversarial
  worst case at 5K rules clears this with wide headroom.
- Deploy on a small instance (1 CPU, 4GB RAM).

Architecture:
API ──────▶ PHREAK Engine ──────▶ Results DB
(1 process, pre-loaded + hot-swapped on rule change)
```

### Scenario 2: E-commerce (100M facts/day, 50K rules)

```
Daily Volume: 100,000,000 facts  (≈ 1,160 facts/sec average;
                                   higher at peak - size for peak, not average)
Rules: 50,000 (pricing, promotions, inventory)

Setup:
- Multiple processes/pods behind a queue. Size N from YOUR measured per-process
  throughput: N ≈ peak facts/sec ÷ (measured facts/sec/process), plus headroom.
- Run perf_realistic_rules.py on your 50K rule set (and --adversarial) first.
- Load balancer (nginx/HAProxy); message queue: Kafka (fault tolerance);
  results store: PostgreSQL with replication.

Architecture:
         Kafka Queue
            │
    ┌───────┼───────┐
    ▼       ▼       ▼       ▼
  API1   API2   API3   API4
  (PHREAK)
    │       │       │       │
    └───────┼───────┘
            ▼
        PostgreSQL
```

### Scenario 3: Financial Risk (500M facts/day, 100K rules)

```
Daily Volume: 500,000,000 facts  (≈ 5,800 facts/sec average; size for peak)
Rules: 100,000 (regulatory, risk, compliance)

Per-fact latency: MEASURE at 100K rules with perf_realistic_rules.py. Per-fact
cost scales with surviving candidates (post-alpha), not raw rule count, so the
number depends on selectivity - do not assume a fixed multiple of the 50K case.

Setup:
- Many processes/pods (size from measured per-process throughput + headroom).
- Pre-load the rule network per pod; hot-swap on rule change (no per-request
  reload).
- Deploy across multiple availability zones.

Architecture:
    Kafka Cluster (distributed)
           │
    ┌──────┼──────┬──────┬──────┐
    ▼      ▼      ▼      ▼      ▼
  K8s Pod × 20 (auto-scaling)
  PHREAK Engine (100K rules)
    │      │      │      │      │
    └──────┼──────┘      └──────┘
           │
      PostgreSQL (sharded)
      + Redis Cache
```

---

## Current Testing Coverage

### Existing Benchmarks

- **Scope:** Single-process, 50K rules maximum
- **File:** `tests/performance/test_benchmark.py`
- **Run:** `pytest tests/performance/test_benchmark.py -v -s`

### What We Test

 10, 100, 1K, 10K, **50K rules** 
 5-200 facts per evaluation 
 Field-level dirty tracking 
 Priority scheduling 
 Segment-based memory management 

### What We Don't Test (Yet)

 Distributed deployment (multi-process, multi-machine) 
 100K+ rules (beyond current single-process limits) 
 Millions of facts in real-time streaming 
 Stateful evaluation with working memory at scale 
 Redis cache performance under high throughput 

---

## Recommended Test Suite for Production Validation

To validate your specific workload (millions of facts, 50K+ rules), implement:

### 1. Streaming Benchmark

```python
# tests/performance/test_streaming.py
import pytest
from fluxrules.engine.phreak import PhreakEngine
import time

def test_phreak_streaming_1m_facts():
    """Validate 1M facts/day throughput with 50K rules."""
    engine = PhreakEngine()
    engine.load_rules(ruleset_50k)
    
    # Simulate 1M facts arriving over 24 hours
    fact_rate = 1_000_000 / (24 * 3600)  # ~12 facts/sec
    
    start = time.time()
    for i in range(1_000_000):
        fact = generate_fact(i)
        result = engine.evaluate(fact)
        assert result is not None
    
    elapsed = time.time() - start
    throughput = 1_000_000 / elapsed
    
    assert throughput > 10_000, f"Expected >10K facts/sec, got {throughput}"
    print(f"Throughput: {throughput:.0f} facts/sec")
```

### 2. Batch Processing Benchmark

```python
# tests/performance/test_batch_processing.py
def test_phreak_batch_1m_facts():
    """Validate batch processing of 1M facts."""
    engine = PhreakEngine()
    engine.load_rules(ruleset_50k)
    
    batch_size = 1000
    total_facts = 1_000_000
    
    start = time.time()
    for batch_idx in range(total_facts // batch_size):
        batch = [generate_fact(i) for i in range(batch_idx * batch_size, (batch_idx + 1) * batch_size)]
        for fact in batch:
            engine.assert_fact(fact)
        # Evaluate the last fact in the batch to flush working memory
        engine.evaluate(batch[-1])
    
    elapsed = time.time() - start
    throughput = total_facts / elapsed
    
    assert throughput > 50_000, f"Expected >50K facts/sec, got {throughput}"
    print(f"Batch Throughput: {throughput:.0f} facts/sec")
```

### 3. Distributed Load Test

```python
# tests/performance/test_distributed.py
# (Run with Docker Compose)
def test_distributed_4_instances_100m_facts():
    """Validate 4-instance deployment handles 100M facts/day."""
    # Deploy 4 instances of FluxRules API
    # Generate load with locust/vegeta
    # Expected: 6K facts/sec collective throughput
```

---

## Production Checklist

Before deploying PHREAK to handle millions of facts:

- [ ] **Baseline:** Run `pytest tests/performance/test_benchmark.py` with your ruleset
- [ ] **Streaming:** Implement test for your expected fact rate (e.g., 10K facts/sec)
- [ ] **Batching:** Measure throughput with batch processing
- [ ] **Memory:** Monitor RSS (resident memory) during load test
- [ ] **Latency:** Track p50, p95, p99 latencies with `latency_tracking=True`
- [ ] **Database:** Stress-test your persistence layer (PostgreSQL/SQLite)
- [ ] **Caching:** Consider Redis for rule network sharing across instances
- [ ] **Monitoring:** Set up Prometheus metrics and alerting
- [ ] **Horizontal Scaling:** Test load balancer failover and auto-scaling

---

## Known Limitations & Future Work

### Current Limitations

1. **Single-Process Baseline:** Standard benchmarks measure one Python process
 - Workaround: Run multiple instances behind a queue (Kafka/Redis)

2. **Working Memory Limits:** Not tested with >1M facts in memory
 - Workaround: Batch evaluation with periodic cleanup

3. **100K+ Rules:** Extrapolated linearly; direct testing pending
 - Workaround: Shard rules by domain (fraud vs. promotions) across instances

4. **Real-Time Validation:** Benchmarks are offline; streaming latency untested
 - Workaround: Use `latency_tracking=True` in production

### Roadmap

- [ ] **v2.1** - Distributed load testing suite (Kafka integration)
- [ ] **v2.2** - Redis-backed rule network caching (cross-process sharing)
- [ ] **v3.0** - Truth Maintenance System (TMS) for stateful rulesets
- [ ] **v4.0** - Complex Event Processing (CEP) for temporal reasoning

---

## Comparison: PHREAK (FluxRules) vs. Drools

| Feature | PHREAK (FluxRules) | Drools (Industry) |
|---------|---|---|
| **50K Rules** | **133ms** | ~50ms |
| **1M Facts/Day** | ** (4-6 instances)** | (1-2 instances) |
| **Delta Evaluation** | Full | Full |
| **Working Memory** | Yes | Yes |
| **TMS** | v3.0 | Yes |
| **CEP** | v4.0 | Yes |
| **Memory (50K)** | **O(active segments)** | Similar |
| **Learning Curve** | Easy (Python) | Steep (Java) |

---

## References & Further Reading

- [Benchmarks](benchmarks.md) - Full benchmark results
- [Algorithm Fidelity](algorithm-fidelity.md) - PHREAK vs. reference evaluator equivalence
- [Custom Engines](custom-engines.md) - Building engines for specialized workloads
- [Deployment Patterns](deployment.md) - How to deploy FluxRules in production

---

## Questions?

See [Contributing](contributing.md) for how to propose load tests or scalability improvements.
