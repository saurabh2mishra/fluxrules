"""
FluxRules Benchmark Suite - P4-01

Benchmarks the PHREAK engine (and the reference evaluator baseline) across
standard workload scenarios.  Results are printed as a table and written to
``docs/benchmarks.md`` when the ``--benchmark-update-docs`` flag is passed.

Also includes multi-condition benchmarks (AND/OR composite rules) that
demonstrate lazy short-circuit evaluation inside condition trees — the primary
workload for real-world rule engines where each rule has 3–6 conditions.

Run::

    pytest tests/performance/test_benchmark.py -v -s

Multi-condition benchmarks only::

    pytest tests/performance/test_benchmark.py -v -s -k multi_condition
"""

from __future__ import annotations

import random
import time
from dataclasses import dataclass
from typing import Any

import pytest

from fluxrules.domain.models import EngineRule as DomainRule
from fluxrules.domain.models import RuleCondition, Ruleset
from fluxrules.services.reference_evaluator import ReferenceEvaluator

#  Generators

SEED = 42
FIELD_NAMES = [
    "amount",
    "age",
    "score",
    "quantity",
    "price",
    "weight",
    "duration",
    "rating",
    "balance",
    "limit",
    "threshold",
    "count",
    "distance",
    "speed",
    "temperature",
    "humidity",
]


def _generate_rules_dicts(n: int, rng: random.Random) -> list[dict]:
    """Generate *n* simple condition rules as dicts (for RuleEngine/PHREAK)."""
    rules = []
    for i in range(n):
        field = rng.choice(FIELD_NAMES)
        op = rng.choice([">", ">=", "<", "<="])
        value = round(rng.uniform(0, 10000), 2)
        rules.append(
            {
                "id": i + 1,
                "name": f"rule_{i + 1}",
                "priority": rng.randint(1, 100),
                "action": f"action_{i + 1}",
                "enabled": True,
                "conditions": {
                    "type": "condition",
                    "field": field,
                    "op": op,
                    "value": value,
                },
            }
        )
    return rules


def _generate_rules_domain(n: int, rng: random.Random) -> tuple[DomainRule, ...]:
    """Generate *n* simple condition rules as domain ``Rule`` objects."""
    rules: list[DomainRule] = []
    for i in range(n):
        field = rng.choice(FIELD_NAMES)
        op_map = {">": "gt", ">=": "gte", "<": "lt", "<=": "lte"}
        op = rng.choice(list(op_map.keys()))
        value = round(rng.uniform(0, 10000), 2)
        rules.append(
            DomainRule(
                id=str(i + 1),
                name=f"rule_{i + 1}",
                condition_nodes=(RuleCondition(fact=field, operator=op_map[op], value=value),),
                actions=(f"action_{i + 1}",),
                priority=rng.randint(1, 100),
            )
        )
    return tuple(rules)


def _generate_facts(n: int, rng: random.Random) -> dict[str, Any]:
    """Generate a fact dict with *n* numeric fields."""
    fields = FIELD_NAMES * ((n // len(FIELD_NAMES)) + 1)
    chosen = fields[:n]
    return {f: round(rng.uniform(0, 10000), 2) for f in chosen}


def _generate_multi_condition_rules_dicts(
    n: int,
    rng: random.Random,
    *,
    min_conditions: int = 3,
    max_conditions: int = 5,
    selective_first: bool = False,
) -> list[dict]:
    """Generate *n* AND-composite rules, each with min–max leaf conditions.

    When *selective_first* is True, the first condition in each AND tree uses
    a tight high-value range (> 8500) so roughly 15% of facts pass it.  This
    is the scenario that maximises short-circuit benefit: for ~85% of rule
    evaluations the engine exits after one condition instead of evaluating all.
    """
    rules = []
    for i in range(n):
        k = rng.randint(min_conditions, max_conditions)
        conditions = []
        for j in range(k):
            field = rng.choice(FIELD_NAMES)
            if j == 0 and selective_first:
                # Tight first gate: ~15% pass rate → ~85% short-circuit exits
                conditions.append(
                    {"type": "condition", "field": field, "op": ">", "value": 8500.0}
                )
            else:
                op = rng.choice([">", ">=", "<", "<="])
                value = round(rng.uniform(0, 10000), 2)
                conditions.append(
                    {"type": "condition", "field": field, "op": op, "value": value}
                )
        rules.append(
            {
                "id": i + 1,
                "name": f"mc_rule_{i + 1}",
                "priority": rng.randint(1, 100),
                "action": f"action_{i + 1}",
                "enabled": True,
                "conditions": {"type": "and", "conditions": conditions},
            }
        )
    return rules


#  Scenario definitions


@dataclass
class Scenario:
    name: str
    rule_count: int
    fact_count: int
    target_ms: float  # upper-bound target for the fastest engine
    iterations: int = 50


@dataclass
class MultiCondScenario:
    name: str
    rule_count: int
    min_conditions: int
    max_conditions: int
    selective_first: bool
    target_ms: float
    iterations: int = 50
    description: str = ""


SCENARIOS = [
    Scenario("Micro (warm)", 10, 5, 0.1, iterations=200),
    Scenario("Small", 100, 20, 1.0, iterations=100),
    Scenario("Medium", 1_000, 50, 10.0, iterations=20),
    Scenario("Large", 10_000, 100, 100.0, iterations=5),
    Scenario("XL", 50_000, 200, 500.0, iterations=2),
]

# Multi-condition scenarios — all use all 16 fields in every fact so the
# bitmask linker cannot prune; cost is purely condition evaluation.
MULTI_COND_SCENARIOS = [
    MultiCondScenario(
        name="MC-Flat-100",
        rule_count=100,
        min_conditions=3,
        max_conditions=5,
        selective_first=False,
        target_ms=2.0,
        iterations=100,
        description="100 rules × 3–5 AND conditions, uniform selectivity",
    ),
    MultiCondScenario(
        name="MC-Flat-500",
        rule_count=500,
        min_conditions=3,
        max_conditions=5,
        selective_first=False,
        target_ms=10.0,
        iterations=50,
        description="500 rules × 3–5 AND conditions, uniform selectivity",
    ),
    MultiCondScenario(
        name="MC-Flat-1000",
        rule_count=1_000,
        min_conditions=3,
        max_conditions=5,
        selective_first=False,
        target_ms=20.0,
        iterations=20,
        description="1 000 rules × 3–5 AND conditions, uniform selectivity",
    ),
    MultiCondScenario(
        name="MC-Selective-100",
        rule_count=100,
        min_conditions=3,
        max_conditions=5,
        selective_first=True,
        target_ms=1.0,
        iterations=100,
        description="100 rules × 3–5 AND conditions, ~85% short-circuit at first gate",
    ),
    MultiCondScenario(
        name="MC-Selective-500",
        rule_count=500,
        min_conditions=3,
        max_conditions=5,
        selective_first=True,
        target_ms=5.0,
        iterations=50,
        description="500 rules × 3–5 AND conditions, ~85% short-circuit at first gate",
    ),
    MultiCondScenario(
        name="MC-Deep-200",
        rule_count=200,
        min_conditions=6,
        max_conditions=8,
        selective_first=False,
        target_ms=5.0,
        iterations=50,
        description="200 rules × 6–8 AND conditions, deep trees",
    ),
]


def _bench(fn, iterations: int) -> float:
    """Return median eval time in **ms** over *iterations* runs."""
    times = []
    for _ in range(iterations):
        t0 = time.perf_counter()
        fn()
        times.append((time.perf_counter() - t0) * 1000)
    times.sort()
    return times[len(times) // 2]


#  Tests

_results: list[dict] = []


@pytest.mark.performance
@pytest.mark.parametrize("scenario", SCENARIOS, ids=[s.name for s in SCENARIOS])
def test_benchmark_reference(scenario: Scenario) -> None:
    rng = random.Random(SEED)
    rules = _generate_rules_domain(scenario.rule_count, rng)
    facts = _generate_facts(scenario.fact_count, rng)
    ruleset = Ruleset(group="bench", rules=rules)
    engine = ReferenceEvaluator()

    ms = _bench(lambda: engine.evaluate(ruleset, facts), scenario.iterations)
    _results.append({"scenario": scenario.name, "engine": "Reference", "ms": ms})
    print(f"  Reference | {scenario.name}: {ms:.3f} ms")


@pytest.mark.performance
@pytest.mark.parametrize("scenario", SCENARIOS, ids=[s.name for s in SCENARIOS])
def test_benchmark_phreak(scenario: Scenario) -> None:
    """Benchmark using the unified PhreakEngine."""
    from fluxrules import Rule as EngineRule
    from fluxrules.engine.phreak import PhreakEngine as UnifiedPhreak

    rng = random.Random(SEED)
    rules_dicts = _generate_rules_dicts(scenario.rule_count, rng)
    facts = _generate_facts(scenario.fact_count, rng)

    engine = UnifiedPhreak()
    engine_rules = []
    for rd in rules_dicts:
        engine_rules.append(
            EngineRule(
                id=rd["id"],
                name=rd["name"],
                conditions=rd["conditions"],
                action=rd.get("action", ""),
                priority=rd.get("priority", 0),
            )
        )
    engine.load_rules(engine_rules)

    ms = _bench(lambda: engine.evaluate(facts), scenario.iterations)
    _results.append({"scenario": scenario.name, "engine": "PHREAK", "ms": ms})
    print(f"  PHREAK      | {scenario.name}: {ms:.3f} ms")


# ---------------------------------------------------------------------------
# Multi-condition benchmarks
# ---------------------------------------------------------------------------


@pytest.mark.performance
@pytest.mark.parametrize(
    "scenario", MULTI_COND_SCENARIOS, ids=[s.name for s in MULTI_COND_SCENARIOS]
)
def test_benchmark_phreak_multi_condition(scenario: MultiCondScenario) -> None:
    """Benchmark PhreakEngine on AND-composite rules with multiple conditions.

    These scenarios exercise the lazy short-circuit path inside
    _evaluate_condition_inner: with *selective_first=True* the engine exits
    after the first failing condition in ~85% of rule evaluations instead of
    evaluating all conditions.  The delta between flat and selective scenarios
    at the same rule count is the measurable gain from generator-based
    short-circuit evaluation.
    """
    from fluxrules import Rule as EngineRule
    from fluxrules.engine.phreak import PhreakEngine as UnifiedPhreak

    rng = random.Random(SEED)
    rules_dicts = _generate_multi_condition_rules_dicts(
        scenario.rule_count,
        rng,
        min_conditions=scenario.min_conditions,
        max_conditions=scenario.max_conditions,
        selective_first=scenario.selective_first,
    )
    # All 16 fields present in every fact — bitmask linker cannot prune,
    # so all cost is in condition evaluation.
    facts = _generate_facts(len(FIELD_NAMES), rng)

    engine = UnifiedPhreak()
    engine.load_rules(
        [
            EngineRule(
                id=rd["id"],
                name=rd["name"],
                conditions=rd["conditions"],
                action=rd.get("action", ""),
                priority=rd.get("priority", 0),
            )
            for rd in rules_dicts
        ]
    )

    ms = _bench(lambda: engine.evaluate(facts), scenario.iterations)
    throughput = round(1000 / ms) if ms > 0 else 0
    avg_cond = (scenario.min_conditions + scenario.max_conditions) / 2
    label = "selective" if scenario.selective_first else "flat"

    _results.append({"scenario": scenario.name, "engine": "PHREAK-MC", "ms": ms})
    print(
        f"  PHREAK-MC [{label:>9}] | {scenario.name}: {ms:.3f} ms"
        f"  ({throughput:>6} eval/s, ~{avg_cond:.0f} cond/rule)"
        f"  — {scenario.description}"
    )
    assert ms < scenario.target_ms, (
        f"{scenario.name}: {ms:.3f} ms exceeds target {scenario.target_ms} ms"
    )


# ---------------------------------------------------------------------------
# Streaming mode benchmarks
# ---------------------------------------------------------------------------


@dataclass
class StreamingScenario:
    name: str
    rule_count: int
    fact_count: int
    iterations: int
    target_unchanged_ms: float  # upper bound for second call when facts are identical


STREAMING_SCENARIOS = [
    StreamingScenario("Stream-100", rule_count=100, fact_count=20, iterations=50, target_unchanged_ms=1.0),
    StreamingScenario("Stream-1000", rule_count=1000, fact_count=50, iterations=20, target_unchanged_ms=2.0),
    StreamingScenario("Stream-5000", rule_count=5000, fact_count=100, iterations=10, target_unchanged_ms=10.0),
]


@pytest.mark.performance
@pytest.mark.parametrize(
    "scenario", STREAMING_SCENARIOS, ids=[s.name for s in STREAMING_SCENARIOS]
)
def test_benchmark_phreak_streaming(scenario: StreamingScenario) -> None:
    """Benchmark PhreakEngine streaming_mode=True across three call patterns.

    - first_call_ms  : first evaluate() on a fresh engine (pays full evaluation cost)
    - unchanged_ms   : repeated calls with identical facts (O(1) short-circuit path)
    - changed_ms     : calls where one field changed (dirty-segment re-evaluation cost)

    Only ``unchanged_ms`` is asserted; first_call_ms and changed_ms are informational.
    """
    from fluxrules import Rule as EngineRule
    from fluxrules.engine.phreak import PhreakEngine as UnifiedPhreak

    rng = random.Random(SEED)
    rules_dicts = _generate_rules_dicts(scenario.rule_count, rng)

    def _make_engine() -> UnifiedPhreak:  # type: ignore[type-arg]
        eng = UnifiedPhreak(streaming_mode=True)
        eng.load_rules(
            [
                EngineRule(
                    id=rd["id"],
                    name=rd["name"],
                    conditions=rd["conditions"],
                    action=rd.get("action", ""),
                    priority=rd.get("priority", 0),
                )
                for rd in rules_dicts
            ]
        )
        return eng

    facts_a = _generate_facts(scenario.fact_count, rng)

    # facts_b: identical to facts_a except one field changed
    facts_b = dict(facts_a)
    changed_field = next(iter(facts_b))
    facts_b[changed_field] = round(facts_b[changed_field] + 1.0, 2)

    # first_call_ms: time the very first evaluate() on a fresh engine (single timing)
    engine_first = _make_engine()
    t0 = time.perf_counter()
    engine_first.evaluate(facts_a)
    first_call_ms = (time.perf_counter() - t0) * 1000

    # unchanged_ms: engine has already seen facts_a; subsequent identical calls are O(1)
    engine_unchanged = _make_engine()
    engine_unchanged.evaluate(facts_a)  # warm-up: pays full cost, establishes baseline
    unchanged_ms = _bench(lambda: engine_unchanged.evaluate(facts_a), scenario.iterations)

    # changed_ms: alternate facts_a → facts_b each iteration so each facts_b call
    # always sees a dirty segment (informational; not asserted)
    engine_changed = _make_engine()
    engine_changed.evaluate(facts_a)  # prime with facts_a
    changed_times = []
    for _ in range(scenario.iterations):
        engine_changed.evaluate(facts_a)  # reset to known-clean state
        t0 = time.perf_counter()
        engine_changed.evaluate(facts_b)  # one field differs → dirty-segment re-eval
        changed_times.append((time.perf_counter() - t0) * 1000)
    changed_times.sort()
    changed_ms = changed_times[len(changed_times) // 2]

    speedup = first_call_ms / unchanged_ms if unchanged_ms > 0 else float("inf")

    print(
        f"  PHREAK-streaming | {scenario.name}: "
        f"first={first_call_ms:.3f} ms  unchanged={unchanged_ms:.4f} ms  "
        f"changed={changed_ms:.3f} ms  speedup={speedup:.1f}x"
    )

    assert unchanged_ms < scenario.target_unchanged_ms, (
        f"{scenario.name}: unchanged_ms={unchanged_ms:.4f} ms "
        f"exceeds target {scenario.target_unchanged_ms} ms"
    )
