"""Benchmarks for the three untested risk areas.

Prior performance work measured only *stateless* evaluation. Three areas carry
real risk, are recommended in the docs, and had no supporting data:

1. **Streaming / stateful working memory** - long-lived sessions doing repeated
   assert/retract. This is where stateful rule engines classically leak: retract
   removes the fact but leaves partial matches, token memory, or index entries
   behind. Measured with ``tracemalloc`` over 10k+ operations.

2. **Cross-fact / beta-network joins** - combinatorial in fact count, and the
   real scaling cliff. A 2-way join over N facts per type is O(N^2) matches in
   the worst case; a 3-way join is O(N^3). We measure where that becomes
   impractical rather than asserting a limit.

3. **Deep nested facts** - facts are flat, so nesting is paid for during
   flattening. We measure flattening cost against nesting depth.

Run directly for a report:

    python tests/performance/perf_risk_areas.py

Each section prints absolute numbers *and* a growth factor, because the growth
factor is what generalises to hardware other than the machine that ran it.
"""

from __future__ import annotations

import gc
import statistics
import time
import tracemalloc
from collections.abc import Callable
from typing import Any

from fluxrules import PhreakEngine, Rule
from fluxrules.engine.cross_fact import CrossFactEngine, CrossFactRule, Pattern
from fluxrules.pipeline.utils.dict_utils import flatten_dict


def _median_ms(fn: Callable[[], Any], repeats: int = 15, warmup: int = 3) -> float:
    for _ in range(warmup):
        fn()
    samples = []
    for _ in range(repeats):
        start = time.perf_counter()
        fn()
        samples.append(time.perf_counter() - start)
    return statistics.median(samples) * 1000


# ---------------------------------------------------------------------------
# 15a. Streaming / stateful working-memory growth
# ---------------------------------------------------------------------------


def _streaming_rules(n: int = 50) -> list[Rule]:
    return [
        Rule(
            id=i + 1,
            name=f"stream_rule_{i}",
            condition_dsl={
                "type": "condition",
                "field": f"metric_{i % 10}",
                "op": ">",
                "value": i % 100,
            },
            action=f"action_{i}",
            persist=False,
        )
        for i in range(n)
    ]


def measure_streaming_memory(
    operations: int = 20_000,
    rules: int = 50,
    sample_every: int = 2_000,
) -> list[tuple[int, int, int]]:
    """Assert/retract in a long-lived session; sample memory as we go.

    Every asserted fact is retracted immediately, so working memory should
    oscillate around a constant size. If retained memory climbs with the
    operation count, state is being kept that retraction did not release.

    Returns ``(operation, retained_kib, live_facts)`` samples.
    """
    engine = PhreakEngine(streaming_mode=True)
    engine.load_rules(_streaming_rules(rules))

    gc.collect()
    tracemalloc.start()
    baseline = tracemalloc.get_traced_memory()[0]

    samples: list[tuple[int, int, int]] = []
    for i in range(1, operations + 1):
        fact_id = engine.assert_fact({f"metric_{i % 10}": i % 1000, "seq": i})
        engine.retract_fact(fact_id)

        if i % sample_every == 0:
            gc.collect()
            current = tracemalloc.get_traced_memory()[0]
            samples.append((i, (current - baseline) // 1024, len(engine.working_memory)))

    tracemalloc.stop()
    return samples


def measure_streaming_accumulation(
    operations: int = 20_000,
    rules: int = 50,
    sample_every: int = 2_000,
) -> list[tuple[int, int, int]]:
    """Assert *without* retracting - the unbounded-growth case.

    This is not a leak; it is the cost of keeping facts. Measuring it gives a
    per-fact memory figure, which is what you need to size a session.
    """
    engine = PhreakEngine(streaming_mode=True)
    engine.load_rules(_streaming_rules(rules))

    gc.collect()
    tracemalloc.start()
    baseline = tracemalloc.get_traced_memory()[0]

    samples: list[tuple[int, int, int]] = []
    for i in range(1, operations + 1):
        engine.assert_fact({f"metric_{i % 10}": i % 1000, "seq": i})
        if i % sample_every == 0:
            gc.collect()
            current = tracemalloc.get_traced_memory()[0]
            samples.append((i, (current - baseline) // 1024, len(engine.working_memory)))

    tracemalloc.stop()
    return samples


# ---------------------------------------------------------------------------
# 15b. Cross-fact / beta-network joins
# ---------------------------------------------------------------------------


def _two_way_rule() -> CrossFactRule:
    return CrossFactRule(
        id=1,
        name="order-by-gold-customer",
        patterns=[
            Pattern("o", "Order", constraints=[("amount", ">", 100)]),
            Pattern(
                "c",
                "Customer",
                constraints=[("tier", "==", "gold")],
                joins=[("id", "==", "o", "customer_id")],
            ),
        ],
    )


def _three_way_rule() -> CrossFactRule:
    return CrossFactRule(
        id=1,
        name="shipment-order-customer",
        patterns=[
            Pattern("o", "Order", constraints=[("amount", ">", 100)]),
            Pattern(
                "c",
                "Customer",
                constraints=[("tier", "==", "gold")],
                joins=[("id", "==", "o", "customer_id")],
            ),
            Pattern(
                "s",
                "Shipment",
                joins=[("order_id", "==", "o", "id")],
            ),
        ],
    )


def measure_join_scaling(
    rule: CrossFactRule,
    sizes: tuple[int, ...] = (100, 250, 500, 1000),
    three_way: bool = False,
) -> dict[int, tuple[float, int]]:
    """Total insert time (ms) and match count as fact count per type grows.

    Each customer id is distinct, so the join is *selective*: N orders against N
    customers yields N matches, not N^2. That is the well-behaved case, and the
    one worth publishing as a safe range.

    Returns ``{n: (total_ms, activations)}``.
    """
    results: dict[int, tuple[float, int]] = {}
    for n in sizes:
        engine = CrossFactEngine()
        engine.load_rules([rule])

        start = time.perf_counter()
        for i in range(n):
            engine.insert("Customer", {"id": i, "tier": "gold"})
        for i in range(n):
            engine.insert("Order", {"id": i, "customer_id": i, "amount": 500})
        if three_way:
            for i in range(n):
                engine.insert("Shipment", {"order_id": i})
        elapsed = (time.perf_counter() - start) * 1000

        results[n] = (elapsed, len(engine.activations()))
    return results


def measure_join_fanout(
    sizes: tuple[int, ...] = (10, 25, 50, 100),
) -> dict[int, tuple[float, int]]:
    """The adversarial case: every order joins every customer.

    All facts share one correlation key, so N orders x N customers produces N^2
    activations. This is the cliff - it exists in every production rule engine and
    is a property of the rule, not the implementation.
    """
    results: dict[int, tuple[float, int]] = {}
    for n in sizes:
        engine = CrossFactEngine()
        engine.load_rules([_two_way_rule()])

        start = time.perf_counter()
        for _ in range(n):
            engine.insert("Customer", {"id": 1, "tier": "gold"})
        for _ in range(n):
            engine.insert("Order", {"id": 1, "customer_id": 1, "amount": 500})
        elapsed = (time.perf_counter() - start) * 1000

        results[n] = (elapsed, len(engine.activations()))
    return results


# ---------------------------------------------------------------------------
# 15c. Deep nested facts
# ---------------------------------------------------------------------------


def _nested_fact(depth: int, breadth: int = 3) -> dict[str, Any]:
    """A fact nested ``depth`` levels, with ``breadth`` scalar leaves per level."""
    node: dict[str, Any] = {f"leaf_{i}": i for i in range(breadth)}
    for level in range(depth):
        node = {f"leaf_{i}": i for i in range(breadth)} | {f"level_{level}": node}
    return node


def measure_nesting_cost(
    depths: tuple[int, ...] = (1, 2, 4, 8, 16, 32),
    breadth: int = 3,
) -> dict[int, tuple[float, float, int]]:
    """Flattening cost and evaluation cost against nesting depth.

    Facts are flat, so depth is paid once during flattening. The question is
    whether that cost is linear in the number of leaves (fine) or worse (a
    trap). Returns ``{depth: (flatten_ms, evaluate_ms, n_keys)}``.
    """
    results: dict[int, tuple[float, float, int]] = {}
    for depth in depths:
        nested = _nested_fact(depth, breadth)
        flat = flatten_dict(nested)

        # A rule addressing the deepest leaf, so evaluation is not trivially
        # short-circuited by a missing key.
        deepest = ".".join(f"level_{i}" for i in reversed(range(depth))) if depth else ""
        field = f"{deepest}.leaf_0" if deepest else "leaf_0"

        engine = PhreakEngine()
        engine.load_rules(
            [
                Rule(
                    id=1,
                    name="deep",
                    condition_dsl={
                        "type": "condition",
                        "field": field,
                        "op": ">=",
                        "value": 0,
                    },
                    action="hit",
                    persist=False,
                )
            ]
        )

        flatten_ms = _median_ms(lambda: flatten_dict(nested))
        evaluate_ms = _median_ms(lambda: engine.evaluate(flat))
        results[depth] = (flatten_ms, evaluate_ms, len(flat))
    return results


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------


def _report_streaming() -> None:
    print("15a. Streaming working memory - assert + retract (should be flat)")
    print("=" * 68)
    print(f"{'ops':>8} | {'retained KiB':>13} | {'live facts':>11}")
    print("-" * 68)
    samples = measure_streaming_memory()
    for ops, kib, live in samples:
        print(f"{ops:>8} | {kib:>13} | {live:>11}")
    first, last = samples[0][1], samples[-1][1]
    print("-" * 68)
    print(f"retained memory {first} KiB -> {last} KiB over {samples[-1][0]} ops")
    print("Flat => retraction releases state. Rising => state is retained.")

    print()
    print("15a. Streaming working memory - assert only (cost of keeping facts)")
    print("=" * 68)
    print(f"{'ops':>8} | {'retained KiB':>13} | {'live facts':>11} | {'B/fact':>8}")
    print("-" * 68)
    for ops, kib, live in measure_streaming_accumulation():
        per_fact = (kib * 1024 / live) if live else 0
        print(f"{ops:>8} | {kib:>13} | {live:>11} | {per_fact:>8.0f}")


def _report_joins() -> None:
    print()
    print("15b. Cross-fact joins - selective (distinct keys, N matches)")
    print("=" * 68)
    print(f"{'facts/type':>11} | {'2-way ms':>10} {'x':>7} | {'3-way ms':>10} {'x':>7}")
    print("-" * 68)
    sizes = (100, 250, 500, 1000)
    two = measure_join_scaling(_two_way_rule(), sizes)
    three = measure_join_scaling(_three_way_rule(), sizes, three_way=True)
    t_base, r_base = two[sizes[0]][0], three[sizes[0]][0]
    for n in sizes:
        print(
            f"{n:>11} | {two[n][0]:>10.1f} {two[n][0] / t_base:>6.1f}x"
            f" | {three[n][0]:>10.1f} {three[n][0] / r_base:>6.1f}x"
        )
    print("-" * 68)
    print(f"fact growth: {sizes[-1] / sizes[0]:.0f}x")

    print()
    print("15b. Cross-fact joins - adversarial fan-out (one shared key, N^2)")
    print("=" * 68)
    print(f"{'facts/type':>11} | {'total ms':>10} {'x':>7} | {'activations':>12}")
    print("-" * 68)
    fan_sizes = (10, 25, 50, 100)
    fan = measure_join_fanout(fan_sizes)
    f_base = fan[fan_sizes[0]][0]
    for n in fan_sizes:
        print(f"{n:>11} | {fan[n][0]:>10.1f} {fan[n][0] / f_base:>6.1f}x | {fan[n][1]:>12}")
    print("-" * 68)
    print(f"fact growth: {fan_sizes[-1] / fan_sizes[0]:.0f}x")


def _report_nesting() -> None:
    print()
    print("15c. Deep nested facts - flatten and evaluate vs depth")
    print("=" * 68)
    print(f"{'depth':>6} | {'keys':>6} | {'flatten ms':>11} | {'evaluate ms':>12}")
    print("-" * 68)
    for depth, (f_ms, e_ms, keys) in measure_nesting_cost().items():
        print(f"{depth:>6} | {keys:>6} | {f_ms:>11.4f} | {e_ms:>12.4f}")


def main() -> None:
    """Print the full risk-area report."""
    _report_streaming()
    _report_joins()
    _report_nesting()


if __name__ == "__main__":
    main()
