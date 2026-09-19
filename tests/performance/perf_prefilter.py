"""Pre-filter benchmark - indexed DB pre-screen before engine eval.

Demonstrates that pushing a rule-derived, B-tree-indexed filter in front of the
engine eliminates the overwhelming majority of facts before the CPU-bound
``evaluate()`` ever runs - the "1000x" path described in
``.research/TEST_RESULTS_VISUAL_SUMMARY.md``.

Backends (selected via --backend, mirrors DatabaseConfig env split):
    sqlite    -> file DB, zero infra (Dev)            [default]
    postgres  -> FLUXRULES_DB_URL must be set         (Prod)

Run::

    python tests/performance/perf_prefilter.py --backend sqlite
    python tests/performance/perf_prefilter.py --backend sqlite --selective
"""

from __future__ import annotations

import argparse
import os
import random
import sys
import time

sys.path.insert(0, "src")

from sqlalchemy import create_engine

from fluxrules import Rule
from fluxrules.engine.phreak import PhreakEngine
from fluxrules.prefilter import FactPreFilterStore, PreFilteredEvaluator

OPS = [">", ">=", "<", "<="]


def _selective_rule(rid: int, n_fields: int, n_conditions: int, threshold: int) -> Rule:
    """A specific rule: AND of N narrow conditions (low match rate)."""
    fields = random.sample(range(n_fields), n_conditions)
    conds = [
        {"type": "condition", "field": f"field_{f}", "op": ">", "value": threshold} for f in fields
    ]
    return Rule(
        id=rid,
        name=f"r{rid}",
        condition_dsl={"type": "and", "conditions": conds},
        persist=False,
    )


def _broad_rule(rid: int, n_fields: int) -> Rule:
    """A low-selectivity single-condition rule (worst case)."""
    f = rid % n_fields
    return Rule(
        id=rid,
        name=f"r{rid}",
        condition_dsl={
            "type": "condition",
            "field": f"field_{f}",
            "op": ">",
            "value": random.randint(0, 1000),
        },
        persist=False,
    )


def _fact(n_fields: int, density: float) -> dict:
    return {
        f"field_{i}": random.randint(0, 1000) for i in range(n_fields) if random.random() < density
    }


def _store(backend: str) -> FactPreFilterStore:
    if backend == "postgres":
        url = os.environ.get("FLUXRULES_DB_URL")
        if not url:
            raise SystemExit("postgres backend requires FLUXRULES_DB_URL")
        return FactPreFilterStore(engine=create_engine(url, future=True))
    # SQLite (Dev) - temp file
    path = os.path.join(os.getcwd(), "prefilter_bench.db")
    return FactPreFilterStore(engine=create_engine(f"sqlite:///{path}", future=True))


def _row(label: str, value: str, unit: str = "") -> None:
    print(f"  {label:<44} {value:>16} {unit}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--backend", choices=["sqlite", "postgres"], default="sqlite")
    parser.add_argument("--selective", action="store_true", help="use selective AND rules")
    parser.add_argument("--rules", type=int, default=10_000)
    parser.add_argument("--facts", type=int, default=50_000)
    parser.add_argument("--fields", type=int, default=50)
    args = parser.parse_args()

    random.seed(0)
    print("=" * 92)
    print(
        f"  PRE-FILTER BENCHMARK  ({args.backend}, "
        f"{'selective' if args.selective else 'broad'} rules)"
    )
    print("=" * 92)

    if args.selective:
        rules = [
            _selective_rule(i, args.fields, n_conditions=4, threshold=950)
            for i in range(args.rules)
        ]
    else:
        rules = [_broad_rule(i, args.fields) for i in range(args.rules)]
    facts = [_fact(args.fields, density=0.8) for _ in range(args.facts)]

    engine = PhreakEngine(streaming_mode=False)
    t0 = time.perf_counter()
    engine.load_rules(rules)
    load_s = time.perf_counter() - t0
    print(f"\nSetup: {args.rules:,} rules, {args.facts:,} facts, {args.fields} fields")
    _row("Engine load time", f"{load_s:.2f}", "s")

    # Baseline: engine over ALL facts
    # warm-up
    for f in facts[:50]:
        engine.evaluate(f)
    t0 = time.perf_counter()
    base_fired = sum(1 for f in facts if engine.evaluate(f).fired_rules)
    base_s = time.perf_counter() - t0
    base_tp = args.facts / base_s
    print("\n-- Baseline (engine over all facts) --")
    _row("Throughput", f"{base_tp:,.0f}", "facts/sec")
    _row("Facts that fired", f"{base_fired:,}", "")
    _row("10M facts extrapolated", f"{10_000_000 / base_tp / 3600:.2f}", "hours")

    # Pre-filtered
    store = _store(args.backend)
    evaluator = PreFilteredEvaluator(engine=engine, store=store)
    t0 = time.perf_counter()
    _, stats = evaluator.run(facts)
    total_s = time.perf_counter() - t0
    pf_tp = args.facts / total_s

    print("\n-- Pre-filtered (indexed store -> engine) --")
    _row("Backend", store.dialect, "")
    _row("Bulk load time", f"{stats.load_seconds:.2f}", "s")
    _row("Filter (query) time", f"{stats.filter_seconds:.2f}", "s")
    _row(
        "Candidates",
        f"{stats.candidate_facts:,}",
        f"({stats.reduction_ratio * 100:.1f}% eliminated)",
    )
    _row("Facts that fired", f"{stats.fired_facts:,}", "")
    _row("Effective throughput", f"{pf_tp:,.0f}", "facts/sec")
    _row("10M facts extrapolated", f"{10_000_000 / pf_tp / 3600:.2f}", "hours")

    speedup = pf_tp / base_tp if base_tp else 0
    print("\n-- Verdict --")
    _row("Pre-filter speedup", f"{speedup:.1f}x", "")
    correctness = "PASS" if stats.fired_facts == base_fired else "FAIL (FALSE NEGATIVE!)"
    _row("Soundness (fired baseline == fired pf)", correctness, "")

    store.dispose()


if __name__ == "__main__":
    main()
