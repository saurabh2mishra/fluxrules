"""Process-based parallel evaluation benchmark.

Measures REAL multi-core speedup using ``engine.evaluate_batch(workers=N)`` and
the older ``evaluate_batch_parallel`` (both process pools), unlike the
in-thread simulation in ``perf_massive_scale.py``. ``evaluate_batch`` returns
full ``EvaluationResult`` objects; ``evaluate_batch_parallel`` returns only
fired rule ids, so the gap between the two is the cost of full results.

Python's GIL prevents threads from parallelizing CPU-bound condition
evaluation, so true throughput scaling requires processes. This script shards
a batch of facts across N worker processes - each running its own engine - and
reports measured throughput and speedup.

Correctness note: ``evaluate_batch_parallel`` uses the public ``evaluate`` API
per fact, so results are identical to single-process evaluation (verified in
``tests/engine/test_parallel_worker_pool.py``). Only work distribution changes.

Run::

    python tests/performance/perf_parallel.py
"""

from __future__ import annotations

import os
import random
import sys
import time

sys.path.insert(0, "src")

from fluxrules import Rule
from fluxrules.engine.phreak import PhreakEngine
from fluxrules.engine.runtime import evaluate_batch_parallel


def _rule(rid: int, field: str, value: int) -> Rule:
    return Rule(
        id=rid,
        name=f"rule_{rid}",
        conditions={"type": "condition", "field": field, "op": ">", "value": value},
        priority=rid % 10,
        domain=f"d{rid % 5}",
        tags=frozenset(),
        persist=False,
    )


def _print(label: str, value: str, unit: str = "") -> None:
    print(f"  {label:<42} {value:>16} {unit}")


def main() -> None:
    print("=" * 90)
    print("  Process-Based Parallel Evaluation")
    print("=" * 90)

    n_rules = 10_000
    n_facts = 4_000
    n_fields = 20

    print(f"\nSetup: {n_rules:,} rules, {n_facts:,} facts, {os.cpu_count()} CPUs\n")
    rules = [_rule(i, f"field_{i % n_fields}", random.randint(0, 1000)) for i in range(n_rules)]
    facts = [
        {f"field_{random.randint(0, n_fields - 1)}": random.randint(0, 1000)}
        for _ in range(n_facts)
    ]

    # Single-process baseline (stateless)
    engine = PhreakEngine(streaming_mode=False)
    engine.load_rules(rules)
    # warm-up
    for f in facts[:50]:
        engine.evaluate(f)

    start = time.perf_counter()
    baseline = [set(engine.evaluate(f).fired_rules) for f in facts]
    single_elapsed = time.perf_counter() - start
    single_tp = n_facts / single_elapsed

    _print("Single-process throughput", f"{single_tp:,.0f}", "facts/sec")
    _print("  10M facts extrapolated", f"{10_000_000 / single_tp / 3600:.2f}", "hours")
    print()

    # Parallel (process pool) across worker counts
    max_workers = min(8, os.cpu_count() or 1)
    worker_counts = [w for w in (2, 4, 8) if w <= max_workers]

    for workers in worker_counts:
        start = time.perf_counter()
        parallel = evaluate_batch_parallel(rules, facts, num_workers=workers, streaming_mode=False)
        ids_elapsed = time.perf_counter() - start

        start = time.perf_counter()
        full = engine.evaluate_batch(facts, workers=workers)
        full_elapsed = time.perf_counter() - start

        # Correctness check: parallel must equal single-process results.
        identical = [set(r) for r in parallel] == baseline and [
            set(r.fired_rules) for r in full
        ] == baseline
        status = "✓ identical" if identical else "✗ MISMATCH"

        print(f"  {workers} workers:")
        _print("    evaluate_batch_parallel (ids)", f"{n_facts / ids_elapsed:,.0f}", "facts/sec")
        _print("    evaluate_batch (full results)", f"{n_facts / full_elapsed:,.0f}", "facts/sec")
        _print("    Speedup vs single (full results)", f"{single_elapsed / full_elapsed:.2f}x")
        _print(
            "    Full results cost vs ids", f"{(full_elapsed / ids_elapsed - 1) * 100:+.0f}", "%"
        )
        _print("    Result correctness", status)
        print()

    print("=" * 90)
    print("  Note: speedup is sub-linear due to process startup + rule-load per")
    print("  worker. For long-running services, load engines once and stream")
    print("  facts to persistent workers to amortize that cost.")
    print("=" * 90)


if __name__ == "__main__":
    # The __main__ guard is REQUIRED: ProcessPoolExecutor uses 'spawn' on macOS,
    # which re-imports this module in each child. Without the guard, children
    # would re-run the benchmark recursively.
    main()
