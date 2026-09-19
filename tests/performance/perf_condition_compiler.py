"""Condition-compiler benchmark + A/B parity.

Isolates the per-rule condition compiler (``compile_conditions``) from the alpha
pre-filter (kept OFF here) so the numbers reflect *only* the cost of evaluating
each rule's boolean tree: compiled closures (inlined AND/OR/NOT, leaves bound to
``evaluate_operator``) vs the recursive dict-walk interpreter.

For each workload it runs the engine with ``compile_conditions`` OFF (oracle) and
ON, and reports:

- throughput (facts/sec) for each
- speedup ON/OFF
- a hard PARITY assertion: ``fired_rules`` MUST be identical ON vs OFF

Compilation must be invisible to results - only faster. The interpreter is the
fallback for ``accumulate`` / unknown nodes, so a workload that mixes those in
still has to pass parity.

Run::

    python tests/performance/perf_condition_compiler.py
    python tests/performance/perf_condition_compiler.py --rules 5000 --facts 20000
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


def _single_leaf_rule(rid: int, n_fields: int) -> Rule:
    """Cheapest rule: one leaf -> interpreter overhead is mostly the dispatch."""
    return Rule(
        id=rid,
        name=f"leaf_{rid}",
        condition_dsl=_leaf(f"field_{rid % n_fields}", ">", 500),
        priority=rid % 10,
        persist=False,
    )


def _deep_and_rule(rid: int, n_fields: int, n_conditions: int = 6) -> Rule:
    """Wide AND of leaves -> the recursion/list-build cost the compiler removes."""
    fields = random.sample(range(n_fields), min(n_conditions, n_fields))
    conditions = [_leaf(f"field_{f}", ">", random.randint(100, 400)) for f in fields]
    return Rule(
        id=rid,
        name=f"and_{rid}",
        condition_dsl={"type": "and", "conditions": conditions},
        priority=rid % 10,
        persist=False,
    )


def _nested_bool_rule(rid: int, n_fields: int) -> Rule:
    """Nested AND/OR/NOT -> exercises the inlined boolean structure end to end."""
    f = lambda j: f"field_{(rid + j) % n_fields}"  # noqa: E731
    dsl = {
        "type": "and",
        "conditions": [
            {
                "type": "or",
                "conditions": [_leaf(f(0), ">", 800), _leaf(f(1), "<", 200)],
            },
            {"type": "not", "condition": _leaf(f(2), "==", 0)},
            _leaf(f(3), ">=", 100),
        ],
    }
    return Rule(
        id=rid,
        name=f"nested_{rid}",
        condition_dsl=dsl,
        priority=rid % 10,
        persist=False,
    )


def _dense_fact(n_fields: int) -> dict:
    return {f"field_{j}": random.randint(0, 1000) for j in range(n_fields)}


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

    # Alpha pre-filter OFF on both engines so we measure ONLY the compiler.
    off = PhreakEngine(compile_conditions=False, alpha_prefilter=False)
    off.load_rules(rules)
    on = PhreakEngine(compile_conditions=True, alpha_prefilter=False)
    on.load_rules(rules)

    out_off, fired_off = _run(off, facts)
    out_on, fired_on = _run(on, facts)

    # correctness gate: identical fired_rules per fact
    mismatches = sum(1 for a, b in zip(fired_off, fired_on) if a != b)
    parity = "PASS ✅" if mismatches == 0 else f"FAIL ❌ ({mismatches} differ)"

    speedup = out_off.seconds / out_on.seconds if out_on.seconds else float("inf")

    print(f"  compile OFF : {out_off.throughput:>10,.0f} facts/s   ({out_off.seconds:.3f}s)")
    print(f"  compile ON  : {out_on.throughput:>10,.0f} facts/s   ({out_on.seconds:.3f}s)")
    print(f"  speedup     : {speedup:>10.2f}x")
    print(f"  fired total OFF/ON       : {out_off.fired_total:,} / {out_on.fired_total:,}")
    print(f"  compiled rules           : {len(on._compiled_conditions):,}")
    print(f"  PARITY (fired_rules)     : {parity}")

    if mismatches:
        raise SystemExit(f"PARITY FAILED on workload '{name}' - condition compiler is unsound!")


def main() -> None:
    ap = argparse.ArgumentParser(description="Condition-compiler benchmark")
    ap.add_argument("--rules", type=int, default=2000)
    ap.add_argument("--facts", type=int, default=3000)
    ap.add_argument("--fields", type=int, default=20)
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args()

    random.seed(args.seed)

    print("\n" + "=" * 90)
    print("  CONDITION-COMPILER BENCHMARK + A/B PARITY")
    print("=" * 90)
    print(
        f"  config: rules={args.rules:,} facts={args.facts:,} fields={args.fields} seed={args.seed}"
    )

    nf = args.fields

    _bench_workload(
        "Single-leaf rules (dispatch overhead)",
        [_single_leaf_rule(i, nf) for i in range(args.rules)],
        [_dense_fact(nf) for _ in range(args.facts)],
    )

    _bench_workload(
        "Deep AND (6 leaves) - recursion/list-build cost",
        [_deep_and_rule(i, nf) for i in range(args.rules)],
        [_dense_fact(nf) for _ in range(args.facts)],
    )

    _bench_workload(
        "Nested AND/OR/NOT - inlined boolean structure",
        [_nested_bool_rule(i, nf) for i in range(args.rules)],
        [_dense_fact(nf) for _ in range(args.facts)],
    )

    print("\n" + "=" * 90)
    print("  ALL WORKLOADS PASSED PARITY ✅  - condition compiler is sound across workloads")
    print("=" * 90 + "\n")


if __name__ == "__main__":
    main()
