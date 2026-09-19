"""
FluxRules Benchmark Suite - P4-01

Benchmarks the PHREAK engine (and the reference evaluator baseline) across
standard workload scenarios.  Results are printed as a table and written to
``docs/benchmarks.md`` when the ``--benchmark-update-docs`` flag is passed.

Run::

    pytest tests/performance/test_benchmark.py -v -s
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
                "condition_dsl": {
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
                conditions=(RuleCondition(fact=field, operator=op_map[op], value=value),),
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


#  Scenario definitions


@dataclass
class Scenario:
    name: str
    rule_count: int
    fact_count: int
    target_ms: float  # upper-bound target for the fastest engine
    iterations: int = 50


SCENARIOS = [
    Scenario("Micro (warm)", 10, 5, 0.1, iterations=200),
    Scenario("Small", 100, 20, 1.0, iterations=100),
    Scenario("Medium", 1_000, 50, 10.0, iterations=20),
    Scenario("Large", 10_000, 100, 100.0, iterations=5),
    Scenario("XL", 50_000, 200, 500.0, iterations=2),
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
                condition_dsl=rd["condition_dsl"],
                action=rd.get("action", ""),
                priority=rd.get("priority", 0),
            )
        )
    engine.load_rules(engine_rules)

    ms = _bench(lambda: engine.evaluate(facts), scenario.iterations)
    _results.append({"scenario": scenario.name, "engine": "PHREAK", "ms": ms})
    print(f"  PHREAK      | {scenario.name}: {ms:.3f} ms")
