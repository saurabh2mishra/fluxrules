"""Fact deduplication benchmark.

Real-world fact streams repeat. ``DedupEvaluator`` memoizes the pure
``evaluate(facts)`` function so repeated facts skip the CPU-bound engine path
entirely. This script measures end-to-end throughput on a stream with a
controllable duplicate ratio and reports the speedup vs. the un-deduplicated
engine.

Correctness is covered by ``tests/engine/test_dedup.py`` (cached result == fresh
evaluate); this script only measures the performance envelope.

Run::

    python tests/performance/perf_dedup.py
"""

from __future__ import annotations

import random
import sys
import time

sys.path.insert(0, "src")

from fluxrules import Rule
from fluxrules.engine.phreak import PhreakEngine
from fluxrules.engine.runtime import DedupEvaluator


def _rule(rid: int, field: str, value: int) -> Rule:
    return Rule(
        id=rid,
        name=f"rule_{rid}",
        condition_dsl={"type": "condition", "field": field, "op": ">", "value": value},
        priority=rid % 10,
        domain=f"d{rid % 5}",
        tags=frozenset(),
        persist=False,
    )


def _print(label: str, value: str, unit: str = "") -> None:
    print(f"  {label:<42} {value:>16} {unit}")


def _make_stream(n_facts: int, n_unique: int, n_fields: int, rng: random.Random):
    """Build a stream of ``n_facts`` facts drawn from ``n_unique`` distinct ones."""
    pool = [{f"field_{j}": rng.randint(0, 1000) for j in range(n_fields)} for _ in range(n_unique)]
    return [pool[rng.randrange(n_unique)] for _ in range(n_facts)]


def _engine(rules) -> PhreakEngine:
    eng = PhreakEngine(streaming_mode=False)
    eng.load_rules(rules)
    return eng


def main() -> None:
    print("=" * 90)
    print("  Fact Deduplication")
    print("=" * 90)

    n_rules = 2_000
    n_facts = 10_000
    n_fields = 20
    rng = random.Random(7)

    rules = [_rule(i, f"field_{i % n_fields}", rng.randint(0, 1000)) for i in range(n_rules)]

    print(f"\nSetup: {n_rules:,} rules, {n_facts:,} facts, {n_fields} fields\n")

    for dup_ratio in (0.0, 0.5, 0.9, 0.99):
        n_unique = max(1, int(n_facts * (1 - dup_ratio)))
        stream = _make_stream(n_facts, n_unique, n_fields, rng)

        baseline = _engine(rules)
        t0 = time.perf_counter()
        for fact in stream:
            baseline.evaluate(fact)
        base_s = time.perf_counter() - t0

        dedup = DedupEvaluator(_engine(rules))
        t0 = time.perf_counter()
        for fact in stream:
            dedup.evaluate(fact)
        dedup_s = time.perf_counter() - t0

        speedup = base_s / dedup_s if dedup_s else float("inf")
        print(f"  duplicate ratio = {dup_ratio:.0%}  ({n_unique:,} unique facts)")
        _print("baseline", f"{n_facts / base_s:,.0f}", "facts/sec")
        _print("dedup", f"{n_facts / dedup_s:,.0f}", "facts/sec")
        _print("hit rate", f"{dedup.stats.hit_rate:.1%}")
        _print("speedup", f"{speedup:.2f}x")
        print()


if __name__ == "__main__":
    main()
