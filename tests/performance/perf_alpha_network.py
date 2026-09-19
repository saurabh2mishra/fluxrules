"""Alpha-network (PredicateIndex) benchmark + A/B parity.

Measures the in-memory alpha pre-filter wired into ``PhreakEngine`` across the
full workload envelope - pathological (every rule matches) → selective (low
match) → AND-heavy (sparse facts). For each workload it runs the engine with
``alpha_prefilter`` OFF (the classic per-rule path, used as the oracle) and ON,
and reports:

- throughput (facts/sec) for each
- speedup ON/OFF
- candidate-rule reduction (how many rules the alpha layer dropped per fact)
- a hard PARITY assertion: ``fired_rules`` MUST be identical ON vs OFF

The parity check is the correctness gate: perf claims are only
meaningful if the optimization is invisible to results.

Run::

    python tests/performance/perf_alpha_network.py
    python tests/performance/perf_alpha_network.py --rules 5000 --facts 20000
"""

from __future__ import annotations

import argparse
import random
import sys
import time
from dataclasses import dataclass

sys.path.insert(0, "src")

from fluxrules import Rule
from fluxrules.engine.phreak import PhreakEngine

# Workload generators


def _leaf(field: str, op: str, value: int) -> dict:
    return {"type": "condition", "field": field, "op": op, "value": value}


def _pathological_rule(rid: int, n_fields: int) -> Rule:
    """Low-selectivity rule: ``field > small`` -> almost every fact matches."""
    return Rule(
        id=rid,
        name=f"path_{rid}",
        condition_dsl=_leaf(f"field_{rid % n_fields}", ">", 0),
        priority=rid % 10,
        persist=False,
    )


def _selective_rule(rid: int, n_fields: int) -> Rule:
    """High-selectivity single-leaf rule: ``field > 990`` -> ~1% match."""
    return Rule(
        id=rid,
        name=f"sel_{rid}",
        condition_dsl=_leaf(f"field_{rid % n_fields}", ">", 990),
        priority=rid % 10,
        persist=False,
    )


def _and_heavy_rule(rid: int, n_fields: int, n_conditions: int = 5) -> Rule:
    """AND of several selective leaves -> very low match (sparse-fact realistic)."""
    fields = random.sample(range(n_fields), min(n_conditions, n_fields))
    conditions = [_leaf(f"field_{f}", ">", random.randint(700, 950)) for f in fields]
    return Rule(
        id=rid,
        name=f"and_{rid}",
        condition_dsl={"type": "and", "conditions": conditions},
        priority=rid % 10,
        persist=False,
    )


def _dense_fact(n_fields: int) -> dict:
    return {f"field_{j}": random.randint(0, 1000) for j in range(n_fields)}


def _sparse_fact(n_fields: int, density: float = 0.4) -> dict:
    return {
        f"field_{j}": random.randint(0, 1000) for j in range(n_fields) if random.random() < density
    }


# Bench harness


@dataclass
class Outcome:
    seconds: float
    fired_total: int
    facts: int

    @property
    def throughput(self) -> float:
        return self.facts / self.seconds if self.seconds else 0.0


def _run(engine: PhreakEngine, facts: list[dict]) -> tuple[Outcome, list[frozenset]]:
    fired_total = 0
    per_fact: list[frozenset] = []
    t = time.perf_counter()
    for fact in facts:
        fired = engine.evaluate(fact).fired_rules
        fired_total += len(fired)
        per_fact.append(frozenset(fired))
    return Outcome(time.perf_counter() - t, fired_total, len(facts)), per_fact


def _bench_workload(name: str, rules: list[Rule], facts: list[dict]) -> None:
    print(f"\n{'=' * 90}\n  WORKLOAD: {name}\n{'=' * 90}")
    print(f"  rules={len(rules):,}  facts={len(facts):,}")

    off = PhreakEngine(alpha_prefilter=False)
    off.load_rules(rules)
    on = PhreakEngine(alpha_prefilter=True)
    on.load_rules(rules)

    out_off, fired_off = _run(off, facts)
    out_on, fired_on = _run(on, facts)

    # correctness gate: identical fired_rules per fact
    mismatches = sum(1 for a, b in zip(fired_off, fired_on) if a != b)
    parity = "PASS ✅" if mismatches == 0 else f"FAIL ❌ ({mismatches} differ)"

    # candidate reduction: how many rules the alpha layer drops per fact
    idx = on._alpha_index
    universe = list(on.rule_repository.rules.keys())
    if idx is not None:
        kept = sum(len(idx.prune(f, list(universe))) for f in facts) / len(facts)
        reduction = 1.0 - (kept / len(universe)) if universe else 0.0
    else:
        kept, reduction = float(len(universe)), 0.0

    speedup = out_off.seconds / out_on.seconds if out_on.seconds else float("inf")

    print(f"  alpha OFF : {out_off.throughput:>10,.0f} facts/s   ({out_off.seconds:.3f}s)")
    print(f"  alpha ON  : {out_on.throughput:>10,.0f} facts/s   ({out_on.seconds:.3f}s)")
    print(f"  speedup   : {speedup:>10.2f}x")
    print(
        f"  avg candidate rules/fact : {kept:>8.1f} of {len(universe):,}  "
        f"({reduction * 100:.1f}% pruned)"
    )
    print(f"  fired total OFF/ON       : {out_off.fired_total:,} / {out_on.fired_total:,}")
    print(f"  unfilterable (pass-through): {idx.pass_through if idx else 'n/a'}")
    print(f"  PARITY (fired_rules)     : {parity}")

    if mismatches:
        raise SystemExit(f"PARITY FAILED on workload '{name}' - alpha filter is unsound!")


def main() -> None:
    ap = argparse.ArgumentParser(description="Alpha-network benchmark")
    ap.add_argument("--rules", type=int, default=2000)
    ap.add_argument("--facts", type=int, default=3000)
    ap.add_argument("--fields", type=int, default=20)
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args()

    random.seed(args.seed)

    print("\n" + "=" * 90)
    print("  ALPHA-NETWORK (PredicateIndex) BENCHMARK + A/B PARITY")
    print("=" * 90)
    print(
        f"  config: rules={args.rules:,} facts={args.facts:,} fields={args.fields} seed={args.seed}"
    )

    nf = args.fields

    # 1) Pathological: every rule matches -> alpha can prune nothing (overhead floor)
    _bench_workload(
        "Pathological (every rule matches, alpha overhead floor)",
        [_pathological_rule(i, nf) for i in range(args.rules)],
        [_dense_fact(nf) for _ in range(args.facts)],
    )

    # 2) Selective: ~1% match -> alpha drops the vast majority (the real win)
    _bench_workload(
        "Selective (single-leaf, ~1% match)",
        [_selective_rule(i, nf) for i in range(args.rules)],
        [_dense_fact(nf) for _ in range(args.facts)],
    )

    # 3) AND-heavy + sparse facts -> realistic low-match, mixed presence
    _bench_workload(
        "AND-heavy (5 leaves) + sparse facts",
        [_and_heavy_rule(i, nf) for i in range(args.rules)],
        [_sparse_fact(nf) for _ in range(args.facts)],
    )

    # 4) Mixed: half selective, half unfilterable (NOT) -> partial pruning + soundness
    mixed = []
    for i in range(args.rules):
        if i % 2 == 0:
            mixed.append(_selective_rule(i, nf))
        else:
            mixed.append(
                Rule(
                    id=i,
                    name=f"not_{i}",
                    condition_dsl={
                        "type": "not",
                        "condition": _leaf(f"field_{i % nf}", "==", 1),
                    },
                    priority=i % 10,
                    persist=False,
                )
            )
    _bench_workload(
        "Mixed (50% selective, 50% unfilterable NOT)",
        mixed,
        [_dense_fact(nf) for _ in range(args.facts)],
    )

    print("\n" + "=" * 90)
    print("  ALL WORKLOADS PASSED PARITY ✅  - alpha filter is sound across the envelope")
    print("=" * 90 + "\n")


if __name__ == "__main__":
    main()
