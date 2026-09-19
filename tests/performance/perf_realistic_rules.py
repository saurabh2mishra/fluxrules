"""P1.3 - Realistic-rule benchmark harness (honest p50/p95/p99).

Why this exists
---------------
The other perf suites (``perf_massive_scale.py``, ``test_phreak_engine_perf.py``)
lean on **single-field synthetic** rules where every fact carries the one hot
field. That hides the failure mode from the trustworthiness analysis (§4.2): a
low-selectivity hot field defeats the alpha pre-filter and forces O(rules) work
per fact. We cannot claim trust at "millions/day" without measuring
**production-like** selectivity and reporting the **honest worst case**.

This harness generates rule sets with **mixed fields, ranges, ``in``-sets, ``==``
and AND/OR depth** at a configurable target **match rate**, then reports, on a
*pre-loaded* engine (no per-request reload - that defect was fixed in P0):

- per-fact latency **p50 / p95 / p99** (the numbers an SRE signs off on),
- candidates/fact before and after the alpha layer + cumulative **prune ratio**,
- throughput (facts/s) and an honest **daily-capacity** projection,
- the **adversarial hot-field** case (alpha cannot prune ⇒ O(rules)/fact),
- a **process-pool** multi-core scaling run via ``evaluate_batch_parallel``.

It is intentionally NOT extrapolated by × 86,400. Daily capacity is reported with
its method stated so the numbers are defensible (replaces the
"billions/day single-thread" claim corrected in P1.4 / ``docs/load-testing.md``).

Run::

    python tests/performance/perf_realistic_rules.py                  # 10k/50k/100k
    python tests/performance/perf_realistic_rules.py --rules 50000
    python tests/performance/perf_realistic_rules.py --adversarial
    python tests/performance/perf_realistic_rules.py --parallel --workers 8

The reusable generators + ``measure`` function are imported by the CI smoke test
(``tests/engine/test_realistic_rules_smoke.py``) to gate a p95 budget on every
fast CI run.
"""

from __future__ import annotations

import argparse
import gc
import json
import math
import os
import platform
import random
import sys
import time
from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field
from datetime import datetime, timezone

sys.path.insert(0, "src")

from fluxrules import Rule
from fluxrules.engine.phreak import PhreakEngine

# Reusable generators


@dataclass
class WorkloadConfig:
    """Knobs describing a realistic rule/fact workload.

    Attributes:
        n_fields: size of the field universe rules/facts draw from.
        field_cardinality: distinct values a field can take (controls
            selectivity of ``==`` / ``in`` predicates).
        p_range / p_eq / p_in: probabilities a leaf is a range / equality /
            membership predicate (should sum to ~1.0).
        max_depth: maximum AND/OR nesting depth for a rule's condition.
        p_or: probability a composite node is an OR (vs AND).
        fact_density: probability each field is present in a generated fact.
        target_threshold_pct: where range thresholds sit in [0, cardinality]
            (higher ⇒ more selective ⇒ lower match rate).
    """

    n_fields: int = 60
    field_cardinality: int = 1000
    p_range: float = 0.55
    p_eq: float = 0.25
    p_in: float = 0.20
    max_depth: int = 2
    p_or: float = 0.30
    fact_density: float = 0.8
    target_threshold_pct: float = 0.85


_RANGE_OPS = (">", ">=", "<", "<=")


def _leaf(rng: random.Random, cfg: WorkloadConfig) -> dict:
    field = f"f{rng.randrange(cfg.n_fields)}"
    roll = rng.random()
    if roll < cfg.p_range:
        op = rng.choice(_RANGE_OPS)
        # Selective threshold: high in range so ``> t`` matches a small tail.
        t = int(cfg.field_cardinality * cfg.target_threshold_pct)
        # Spread thresholds a little so signatures vary realistically.
        t += rng.randint(-50, 50)
        return {"type": "condition", "field": field, "op": op, "value": t}
    if roll < cfg.p_range + cfg.p_eq:
        return {
            "type": "condition",
            "field": field,
            "op": "==",
            "value": rng.randrange(cfg.field_cardinality),
        }
    # membership (``in``)
    k = rng.randint(2, 5)
    members = [rng.randrange(cfg.field_cardinality) for _ in range(k)]
    return {"type": "condition", "field": field, "op": "in", "value": members}


def _condition(rng: random.Random, cfg: WorkloadConfig, depth: int) -> dict:
    if depth <= 0 or rng.random() < 0.4:
        return _leaf(rng, cfg)
    n_children = rng.randint(2, 3)
    children = [_condition(rng, cfg, depth - 1) for _ in range(n_children)]
    ctype = "or" if rng.random() < cfg.p_or else "and"
    return {"type": ctype, "conditions": children}


def generate_rules(n_rules: int, cfg: WorkloadConfig, rng: random.Random) -> list[Rule]:
    """Generate ``n_rules`` realistic mixed-field rules."""
    rules: list[Rule] = []
    for rid in range(n_rules):
        dsl = _condition(rng, cfg, cfg.max_depth)
        rules.append(
            Rule(
                id=rid,
                name=f"r{rid}",
                condition_dsl=dsl,
                priority=rid % 10,
                domain=f"d{rid % 8}",
                tags=frozenset({f"t{rid % 4}"}),
                persist=False,
            )
        )
    return rules


def generate_adversarial_rules(n_rules: int, cfg: WorkloadConfig, rng: random.Random) -> list[Rule]:
    """The §4.2 worst case: most rules test one *low-selectivity* hot field.

    Every fact will carry ``hot`` with a value that passes the loose threshold,
    so the value-aware alpha layer cannot prune ⇒ O(rules) candidates per fact.
    A small minority of rules use other fields so the set is not degenerate.
    """
    rules: list[Rule] = []
    for rid in range(n_rules):
        if rng.random() < 0.9:
            # Loose threshold near 0 ⇒ almost every fact's hot value passes.
            dsl = {"type": "condition", "field": "hot", "op": ">", "value": 1}
        else:
            dsl = _leaf(rng, cfg)
        rules.append(
            Rule(
                id=rid,
                name=f"r{rid}",
                condition_dsl=dsl,
                priority=rid % 10,
                domain="d0",
                tags=frozenset(),
                persist=False,
            )
        )
    return rules


def generate_facts(
    n_facts: int, cfg: WorkloadConfig, rng: random.Random, *, adversarial: bool = False
) -> list[dict]:
    """Generate a fact stream; adversarial facts always carry the hot field."""
    facts: list[dict] = []
    for _ in range(n_facts):
        fact = {
            f"f{i}": rng.randrange(cfg.field_cardinality)
            for i in range(cfg.n_fields)
            if rng.random() < cfg.fact_density
        }
        if adversarial:
            fact["hot"] = rng.randrange(cfg.field_cardinality)
        facts.append(fact)
    return facts


def iter_facts(
    n_facts: int,
    cfg: WorkloadConfig,
    rng: random.Random,
    *,
    adversarial: bool = False,
) -> Iterator[dict]:
    """Yield ``n_facts`` facts one at a time (O(1) memory for the stream).

    The materialized ``generate_facts`` costs GBs at 1e6 facts; readiness
    streaming pulls from this generator so only the engine + latency array are
    resident.
    """
    for _ in range(n_facts):
        fact = {
            f"f{i}": rng.randrange(cfg.field_cardinality)
            for i in range(cfg.n_fields)
            if rng.random() < cfg.fact_density
        }
        if adversarial:
            fact["hot"] = rng.randrange(cfg.field_cardinality)
        yield fact


# Measurement


def _percentile(sorted_vals: list[float], pct: float) -> float:
    """Nearest-rank percentile of an already-sorted list (pct in [0, 100]).

    Uses the standard nearest-rank method: rank = ceil(pct/100 × N), clamped to
    [1, N]. For 1..100 this gives p50=50, p95=95, p99=99 (no off-by-one).
    """
    n = len(sorted_vals)
    if n == 0:
        return 0.0
    rank = math.ceil(pct / 100.0 * n)
    k = min(max(rank, 1), n) - 1  # 1-based rank → 0-based index
    return sorted_vals[k]


@dataclass
class BenchReport:
    n_rules: int
    n_facts: int
    load_seconds: float
    p50_ms: float
    p95_ms: float
    p99_ms: float
    throughput_fps: float
    fired_facts: int
    prefilter: dict = field(default_factory=dict)

    def daily_capacity(self) -> float:
        """Honest single-process daily capacity = sustained throughput × seconds/day.

        This is *measured* sustained per-fact throughput on a pre-loaded engine,
        multiplied by 86,400 s - and reported alongside p95/p99 so the headroom
        is explicit. It is NOT idealized batch throughput; see the §7 methodology.
        """
        return self.throughput_fps * 86_400


def measure(
    rules: list[Rule],
    facts: list[dict],
    *,
    alpha: bool = True,
    warmup: int = 50,
) -> BenchReport:
    """Load ``rules`` once, evaluate ``facts``, return per-fact latency stats.

    The engine is built **once** (P0: no per-request reload) and GC is disabled
    during the timed loop so the numbers reflect matcher cost, not collector
    pauses. Per-fact latencies are captured individually for honest percentiles.
    """
    engine = PhreakEngine(alpha_prefilter=alpha)
    t0 = time.perf_counter()
    engine.load_rules(rules)
    load_s = time.perf_counter() - t0

    for f in facts[:warmup]:
        engine.evaluate(f)
    engine.reset_prefilter_stats()

    latencies: list[float] = []
    fired = 0
    gc_was_enabled = gc.isenabled()
    gc.disable()
    try:
        for f in facts:
            s = time.perf_counter()
            res = engine.evaluate(f)
            latencies.append((time.perf_counter() - s) * 1000.0)
            if res.fired_rules:
                fired += 1
    finally:
        if gc_was_enabled:
            gc.enable()

    latencies.sort()
    total_s = sum(latencies) / 1000.0
    throughput = len(facts) / total_s if total_s else float("inf")
    return BenchReport(
        n_rules=len(rules),
        n_facts=len(facts),
        load_seconds=load_s,
        p50_ms=_percentile(latencies, 50),
        p95_ms=_percentile(latencies, 95),
        p99_ms=_percentile(latencies, 99),
        throughput_fps=throughput,
        fired_facts=fired,
        prefilter=engine.get_prefilter_stats(),
    )


def measure_stream(
    rules: list[Rule],
    fact_iter: Iterable[dict],
    *,
    alpha: bool = True,
    warmup: int = 50,
) -> BenchReport:
    """Streaming variant of ``measure`` that never materializes the fact list.

    Facts are pulled from ``fact_iter`` one at a time so a >=1e6-fact stream
    stays memory-flat (only the engine and the latency array are resident). The
    first ``warmup`` facts prime caches and are excluded from the reported
    percentiles/throughput, exactly like ``measure``.
    """
    engine = PhreakEngine(alpha_prefilter=alpha)
    t0 = time.perf_counter()
    engine.load_rules(rules)
    load_s = time.perf_counter() - t0

    it = iter(fact_iter)
    for _ in range(warmup):
        try:
            engine.evaluate(next(it))
        except StopIteration:
            break
    engine.reset_prefilter_stats()

    latencies: list[float] = []
    fired = 0
    n = 0
    gc_was_enabled = gc.isenabled()
    gc.disable()
    try:
        for f in it:
            s = time.perf_counter()
            res = engine.evaluate(f)
            latencies.append((time.perf_counter() - s) * 1000.0)
            if res.fired_rules:
                fired += 1
            n += 1
    finally:
        if gc_was_enabled:
            gc.enable()

    latencies.sort()
    total_s = sum(latencies) / 1000.0
    throughput = n / total_s if total_s else float("inf")
    return BenchReport(
        n_rules=len(rules),
        n_facts=n,
        load_seconds=load_s,
        p50_ms=_percentile(latencies, 50),
        p95_ms=_percentile(latencies, 95),
        p99_ms=_percentile(latencies, 99),
        throughput_fps=throughput,
        fired_facts=fired,
        prefilter=engine.get_prefilter_stats(),
    )


def _environment() -> dict:
    """Machine/interpreter facts recorded alongside every committed artifact."""
    return {
        "python_version": platform.python_version(),
        "implementation": platform.python_implementation(),
        "platform": platform.platform(),
        "machine": platform.machine(),
        "processor": platform.processor() or platform.machine(),
        "cpu_count": os.cpu_count(),
    }


def _peak_memory_mb() -> float:
    """Process peak RSS in MiB (ru_maxrss is bytes on macOS, KiB on Linux)."""
    import resource

    ru = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return ru / (1024 * 1024) if sys.platform == "darwin" else ru / 1024


def parity_fired(rules: list[Rule], facts: list[dict], sample: int) -> dict:
    """Correctness parity: alpha-prefilter ON must fire the same rules as OFF.

    The prefilter is an optimization; it must never change results. We evaluate
    ``sample`` facts through both an alpha-on and an alpha-off engine and compare
    the fired-rule set per fact. Any mismatch is a correctness bug, not a perf
    one, so the artifact records it explicitly.
    """
    on = PhreakEngine(alpha_prefilter=True)
    on.load_rules(rules)
    off = PhreakEngine(alpha_prefilter=False)
    off.load_rules(rules)
    n = min(sample, len(facts))
    mismatches = 0
    for f in facts[:n]:
        if frozenset(on.evaluate(f).fired_rules) != frozenset(off.evaluate(f).fired_rules):
            mismatches += 1
    return {"sample_facts": n, "mismatches": mismatches, "parity_ok": mismatches == 0}


# Reporting


def _row(label: str, value: str, unit: str = "") -> None:
    print(f"  {label:<40} {value:>18} {unit}")


def _print_report(title: str, rep: BenchReport) -> None:
    print(f"\n-- {title} --")
    _row("Rules / facts", f"{rep.n_rules:,} / {rep.n_facts:,}")
    _row("Engine load (once)", f"{rep.load_seconds:.2f}", "s")
    _row("Per-fact p50", f"{rep.p50_ms:.3f}", "ms")
    _row("Per-fact p95", f"{rep.p95_ms:.3f}", "ms")
    _row("Per-fact p99", f"{rep.p99_ms:.3f}", "ms")
    _row("Throughput", f"{rep.throughput_fps:,.0f}", "facts/s")
    _row("Facts that fired ≥1 rule", f"{rep.fired_facts:,}", f"/ {rep.n_facts:,}")
    pf = rep.prefilter
    if pf.get("enabled"):
        _row("Alpha engaged", str(pf.get("engaged")))
        _row("Alpha signatures", f"{pf.get('signature_count', 0):,}")
        _row(
            "Candidates/fact (in → out)",
            f"{pf.get('candidates_in', 0) / max(1, pf.get('facts', 1)):.1f}"
            f" → {pf.get('candidates_out', 0) / max(1, pf.get('facts', 1)):.1f}",
        )
        _row("Alpha prune ratio", f"{pf.get('prune_ratio', 0.0) * 100:.1f}", "%")
    _row("Daily capacity (1 proc)", f"{rep.daily_capacity() / 1e6:,.1f}", "M facts/day")


def run_scales(
    scales: list[int],
    n_facts: int,
    cfg: WorkloadConfig,
    seed: int,
) -> None:
    for n_rules in scales:
        rng = random.Random(seed)
        rules = generate_rules(n_rules, cfg, rng)
        facts = generate_facts(n_facts, cfg, rng)
        rep = measure(rules, facts, alpha=True)
        _print_report(f"Realistic mixed rules - {n_rules:,} rules", rep)


def run_adversarial(n_rules: int, n_facts: int, cfg: WorkloadConfig, seed: int) -> None:
    rng = random.Random(seed)
    rules = generate_adversarial_rules(n_rules, cfg, rng)
    facts = generate_facts(n_facts, cfg, rng, adversarial=True)
    rep = measure(rules, facts, alpha=True)
    _print_report(f"ADVERSARIAL hot-field - {n_rules:,} rules (alpha cannot prune)", rep)
    print(
        "  NOTE: this is the honest worst case. Most rules test one "
        "low-selectivity\n        field every fact carries, so the alpha layer "
        "cannot prune and per-fact\n        cost is O(rules). Plan capacity for "
        "this if your real rules look like this."
    )


def run_parallel(n_rules: int, n_facts: int, cfg: WorkloadConfig, seed: int, workers: int) -> None:
    from fluxrules.engine.runtime import evaluate_batch_parallel

    rng = random.Random(seed)
    rules = generate_rules(n_rules, cfg, rng)
    facts = generate_facts(n_facts, cfg, rng)

    # Single-process baseline throughput for the same workload.
    base = measure(rules, facts, alpha=True)

    print(f"\n-- Process-pool scaling - {n_rules:,} rules, {workers} workers --")
    print(
        "  NOTE: the parallel timing INCLUDES each worker building its own engine\n"
        "        (loading all rules once). With enough facts this amortizes; with\n"
        "        few facts the per-worker build dominates and understates scaling."
    )
    t0 = time.perf_counter()
    results = evaluate_batch_parallel(
        rules=rules, facts=facts, num_workers=workers, streaming_mode=False
    )
    par_s = time.perf_counter() - t0
    par_tp = len(facts) / par_s if par_s else float("inf")
    fired = sum(1 for r in results if r)
    _row("Facts evaluated", f"{len(facts):,}")
    _row("Single-process throughput", f"{base.throughput_fps:,.0f}", "facts/s")
    _row("Parallel throughput", f"{par_tp:,.0f}", "facts/s")
    _row("Speedup", f"{par_tp / base.throughput_fps:.1f}", f"x on {workers} workers")
    _row("Per-core throughput", f"{par_tp / workers:,.0f}", "facts/s/core")
    _row("Facts fired (parity check)", f"{fired:,}", f"/ {len(facts):,}")
    _row("Daily capacity (parallel)", f"{par_tp * 86_400 / 1e6:,.1f}", "M facts/day")


def _workload_dict(cfg: WorkloadConfig) -> dict:
    return {
        "n_fields": cfg.n_fields,
        "field_cardinality": cfg.field_cardinality,
        "p_range": cfg.p_range,
        "p_eq": cfg.p_eq,
        "p_in": cfg.p_in,
        "max_depth": cfg.max_depth,
        "p_or": cfg.p_or,
        "fact_density": cfg.fact_density,
        "target_threshold_pct": cfg.target_threshold_pct,
    }


def run_readiness(
    n_rules: int,
    n_facts: int,
    cfg: WorkloadConfig,
    seed: int,
    workers: int,
    parity_facts: int,
    parallel_facts: int,
    json_path: str | None,
) -> dict:
    """Produce the two committed evidence-gap artifacts (streaming + parallel).

    1. **Streaming readiness** - load ``n_rules`` (>=1000) rules once, stream
       ``n_facts`` (>=1e6) facts through a pre-loaded engine, report p50/p95/p99,
       throughput, peak RSS, and alpha-on-vs-off correctness parity.
    2. **Horizontal scaling** - the same rules over a process pool, reporting
       speedup, per-core throughput, and a fired-facts parity check vs the
       single-process baseline.

    Numbers are *measured on this machine* and stamped with the environment so
    the artifact is reproducible and honest (no ×86,400 extrapolation of an
    idealized batch).
    """
    from fluxrules.engine.runtime import evaluate_batch_parallel

    warmup = 50

    # --- 1) Single-process streaming readiness (memory-flat via a generator).
    rng = random.Random(seed)
    rules = generate_rules(n_rules, cfg, rng)
    stream = iter_facts(n_facts + warmup, cfg, rng)
    print(f"\n-- Streaming readiness: {n_rules:,} rules x {n_facts:,} facts (single process) --")
    rep = measure_stream(rules, stream, alpha=True, warmup=warmup)
    peak_mb = _peak_memory_mb()  # high-water mark right after the streaming run

    # Correctness parity on a bounded, materialized sample (fresh seed stream).
    parity_rng = random.Random(seed + 1)
    parity_sample = generate_facts(parity_facts, cfg, parity_rng)
    parity = parity_fired(rules, parity_sample, parity_facts)

    streaming_artifact = {
        "benchmark": "streaming_readiness",
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "environment": _environment(),
        "workload": _workload_dict(cfg),
        "seed": seed,
        "n_rules": rep.n_rules,
        "n_facts_streamed": rep.n_facts,
        "warmup_facts": warmup,
        "load_seconds": round(rep.load_seconds, 4),
        "latency_ms": {
            "p50": round(rep.p50_ms, 5),
            "p95": round(rep.p95_ms, 5),
            "p99": round(rep.p99_ms, 5),
        },
        "throughput_facts_per_s": round(rep.throughput_fps, 1),
        "daily_capacity_facts": round(rep.daily_capacity(), 0),
        "facts_that_fired_ge1_rule": rep.fired_facts,
        "peak_memory_mb": round(peak_mb, 1),
        "alpha_prefilter": rep.prefilter,
        "correctness_parity_alpha_on_vs_off": parity,
    }
    _print_report("Streaming readiness", rep)
    _row("Peak RSS", f"{peak_mb:,.1f}", "MiB")
    _row(
        "Alpha on/off parity",
        f"{parity['mismatches']} mismatches / {parity['sample_facts']:,} facts",
    )

    # --- 2) Horizontal (multi-process) scaling.
    par_rng = random.Random(seed + 2)
    par_facts_list = generate_facts(parallel_facts, cfg, par_rng)
    base = measure(rules, par_facts_list, alpha=True)
    single_fired = base.fired_facts

    print(
        f"\n-- Horizontal scaling: {n_rules:,} rules x {parallel_facts:,} facts, "
        f"{workers} workers --"
    )
    t0 = time.perf_counter()
    results = evaluate_batch_parallel(
        rules=rules, facts=par_facts_list, num_workers=workers, streaming_mode=False
    )
    par_s = time.perf_counter() - t0
    par_tp = len(par_facts_list) / par_s if par_s else float("inf")
    par_fired = sum(1 for r in results if r)
    speedup = par_tp / base.throughput_fps if base.throughput_fps else float("inf")

    scaling_artifact = {
        "benchmark": "horizontal_scaling",
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "environment": _environment(),
        "workload": _workload_dict(cfg),
        "seed": seed,
        "n_rules": n_rules,
        "n_facts": len(par_facts_list),
        "workers": workers,
        "single_process_throughput_fps": round(base.throughput_fps, 1),
        "parallel_throughput_fps": round(par_tp, 1),
        "speedup_x": round(speedup, 2),
        "per_core_throughput_fps": round(par_tp / workers, 1),
        "parallel_daily_capacity_facts": round(par_tp * 86_400, 0),
        "fired_facts_parity": {
            "single_process": single_fired,
            "parallel": par_fired,
            "parity_ok": single_fired == par_fired,
        },
    }
    _row("Single-process throughput", f"{base.throughput_fps:,.0f}", "facts/s")
    _row("Parallel throughput", f"{par_tp:,.0f}", "facts/s")
    _row("Speedup", f"{speedup:.2f}", f"x on {workers} workers")
    _row("Per-core throughput", f"{par_tp / workers:,.0f}", "facts/s/core")
    _row(
        "Fired-facts parity",
        f"single={single_fired:,} parallel={par_fired:,} "
        f"({'OK' if single_fired == par_fired else 'MISMATCH'})",
    )

    bundle = {
        "streaming_readiness": streaming_artifact,
        "horizontal_scaling": scaling_artifact,
    }
    if json_path:
        with open(json_path, "w", encoding="utf-8") as fh:
            json.dump(bundle, fh, indent=2, sort_keys=True)
        print(f"\n  wrote artifact: {json_path}")
    return bundle


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--rules",
        type=int,
        nargs="*",
        help="rule scales to run (default: 10000 50000 100000)",
    )
    parser.add_argument("--facts", type=int, default=2000, help="facts per scale")
    parser.add_argument(
        "--adversarial", action="store_true", help="also run the hot-field worst case"
    )
    parser.add_argument(
        "--parallel", action="store_true", help="run the process-pool scaling benchmark"
    )
    parser.add_argument(
        "--workers", type=int, default=0, help="worker processes (0 ⇒ os.cpu_count())"
    )
    parser.add_argument(
        "--readiness",
        action="store_true",
        help="run the two evidence-gap benchmarks (streaming + scaling) and, with "
        "--json, write a committed artifact",
    )
    parser.add_argument("--readiness-rules", type=int, default=1000, help="rules for --readiness")
    parser.add_argument(
        "--readiness-facts",
        type=int,
        default=1_000_000,
        help="facts streamed for --readiness",
    )
    parser.add_argument(
        "--parity-facts",
        type=int,
        default=100_000,
        help="facts for the alpha on/off correctness parity sample",
    )
    parser.add_argument(
        "--parallel-facts",
        type=int,
        default=200_000,
        help="facts for the --readiness horizontal-scaling run",
    )
    parser.add_argument("--json", type=str, default=None, help="write artifact JSON here")
    parser.add_argument("--seed", type=int, default=2024)
    args = parser.parse_args()

    cfg = WorkloadConfig()

    if args.readiness:
        workers = args.workers or (os.cpu_count() or 1)
        run_readiness(
            n_rules=args.readiness_rules,
            n_facts=args.readiness_facts,
            cfg=cfg,
            seed=args.seed,
            workers=workers,
            parity_facts=args.parity_facts,
            parallel_facts=args.parallel_facts,
            json_path=args.json,
        )
        print("\n" + "=" * 80)
        return

    scales = args.rules or [10_000, 50_000, 100_000]

    print("=" * 80)
    print("  REALISTIC-RULE BENCHMARK (mixed fields/ops/depth, pre-loaded engine)")
    print("=" * 80)
    print(
        "  Methodology: engine built ONCE (no per-request reload); GC paused "
        "during\n  the timed loop; per-fact latencies captured individually; "
        "daily capacity =\n  measured sustained throughput × 86,400 s (stated, "
        "not idealized)."
    )

    run_scales(scales, args.facts, cfg, args.seed)

    if args.adversarial:
        run_adversarial(scales[0], args.facts, cfg, args.seed)

    if args.parallel:
        workers = args.workers or (os.cpu_count() or 1)

        workers = args.workers or (os.cpu_count() or 1)
        # Use plenty of facts so each worker's one-time engine build amortizes
        # and the measured speedup reflects steady-state matching, not setup.
        par_facts = max(args.facts, 400 * workers)
        run_parallel(scales[0], par_facts, cfg, args.seed, workers)

    print("\n" + "=" * 80)


if __name__ == "__main__":
    main()
