"""Stateless/streaming equivalence tests.

Hard requirement: *Irrespective of which evaluation path PHREAK takes, the
effective set of fired rules must be identical.* These tests pin that invariant
so performance optimizations (NodeMemory caching, value indexing, hierarchical
segments, etc.) can never introduce an algorithmic gap between the stateless and
streaming paths.

Two distinct contracts are tested separately:

1. Full-set equivalence (the user-facing guarantee):
   For a given fact state, ``PhreakEngine`` (stateless) and a *fresh*
   ``PhreakEngine`` (streaming, first sight of the fact) must fire exactly the
   same rule IDs.

2. Streaming delta contract (documented optimization):
   When the SAME fact is evaluated again on a streaming engine, it reports an
   empty delta (nothing changed). This is intentional and is verified on its
   own so it can never silently drift.
"""

from __future__ import annotations

import random

import pytest

from fluxrules import Rule
from fluxrules.engine.phreak import PhreakEngine


def _leaf(rid: int, field: str, op: str, value) -> Rule:
    return Rule(
        id=rid,
        name=f"rule_{rid}",
        condition_dsl={"type": "condition", "field": field, "op": op, "value": value},
        priority=rid % 5,
        domain=f"d{rid % 3}",
        tags=frozenset([f"t{rid % 2}"]),
        persist=False,
    )


def _and(rid: int, conditions: list[dict]) -> Rule:
    return Rule(
        id=rid,
        name=f"rule_{rid}",
        condition_dsl={"type": "and", "conditions": conditions},
        priority=rid % 5,
        domain=f"d{rid % 3}",
        tags=frozenset(),
        persist=False,
    )


def _or(rid: int, conditions: list[dict]) -> Rule:
    return Rule(
        id=rid,
        name=f"rule_{rid}",
        condition_dsl={"type": "or", "conditions": conditions},
        priority=rid % 5,
        domain=f"d{rid % 3}",
        tags=frozenset(),
        persist=False,
    )


def _fired_set(engine, facts) -> set[int]:
    """Return the set of fired rule IDs (order-independent comparison)."""
    return set(engine.evaluate(facts).fired_rules)


def _fresh_stateless(rules: list[Rule]) -> PhreakEngine:
    eng = PhreakEngine(streaming_mode=False)
    eng.load_rules(rules)
    return eng


def _fresh_streaming(rules: list[Rule]) -> PhreakEngine:
    eng = PhreakEngine(streaming_mode=True)
    eng.load_rules(rules)
    return eng


def _full_set_engines(rules: list[Rule]):
    """Engines whose ``evaluate`` returns the FULL fired set every call.

    Streaming is excluded here because it reports deltas; it is covered by a
    fresh-engine-per-fact comparison and by the delta-contract test.
    """
    return {
        "phreak_stateless": _fresh_stateless(rules),
    }


def _assert_full_set_agreement(rules: list[Rule], engines: dict, facts: dict) -> set[int]:
    """Assert stateless engines AND a fresh streaming engine all agree.

    The fresh streaming engine sees ``facts`` for the first time, so it must
    report the complete fired set (delta from empty == full set).
    """
    results = {name: _fired_set(eng, facts) for name, eng in engines.items()}
    # A fresh streaming engine on first sight must equal the stateless full set.
    results["phreak_streaming_fresh"] = _fired_set(_fresh_streaming(rules), facts)

    reference_name, reference = next(iter(results.items()))
    for name, fired in results.items():
        assert fired == reference, (
            f"Engine '{name}' disagreed with '{reference_name}' for facts={facts}.\n"
            f"  {name}: {sorted(fired)}\n"
            f"  {reference_name}: {sorted(reference)}\n"
            f"  only in {name}: {sorted(fired - reference)}\n"
            f"  only in {reference_name}: {sorted(reference - fired)}"
        )
    return reference


# Full-set equivalence: stateless Phreak vs fresh streaming Phreak


class TestFullSetEquivalence:
    def test_simple_leaf_rules(self):
        rules = [
            _leaf(1, "amount", ">", 100),
            _leaf(2, "amount", "<", 50),
            _leaf(3, "status", "==", "active"),
        ]
        engines = _full_set_engines(rules)
        for facts in (
            {"amount": 150, "status": "active"},
            {"amount": 30},
            {"amount": 75, "status": "inactive"},
            {"status": "active"},
            {},
        ):
            _assert_full_set_agreement(rules, engines, facts)

    def test_and_or_composites(self):
        rules = [
            _and(
                1,
                [
                    {"type": "condition", "field": "age", "op": ">=", "value": 18},
                    {
                        "type": "condition",
                        "field": "country",
                        "op": "==",
                        "value": "US",
                    },
                ],
            ),
            _or(
                2,
                [
                    {"type": "condition", "field": "vip", "op": "==", "value": True},
                    {"type": "condition", "field": "amount", "op": ">", "value": 1000},
                ],
            ),
        ]
        engines = _full_set_engines(rules)
        for facts in (
            {"age": 25, "country": "US"},
            {"age": 25, "country": "UK"},
            {"vip": True},
            {"amount": 5000},
            {"age": 17, "country": "US", "vip": False, "amount": 10},
            {},
        ):
            _assert_full_set_agreement(rules, engines, facts)

    def test_absent_vs_null_fields(self):
        """A missing field must behave identically across engines.

        Guards the NodeMemory cache-key sentinel (_ABSENT): an absent field must
        never share a cache entry with a field present as None.
        """
        rules = [
            _leaf(1, "x", "==", None),
            _leaf(2, "x", "!=", 5),
            _leaf(3, "x", ">", 0),
        ]
        engines = _full_set_engines(rules)
        for facts in (
            {"x": None},
            {},  # x absent
            {"x": 0},
            {"x": 5},
            {"x": 10},
        ):
            _assert_full_set_agreement(rules, engines, facts)


class TestRandomizedFullSetEquivalence:
    @pytest.mark.parametrize("seed", list(range(10)))
    def test_random_leaf_rulesets(self, seed: int):
        rng = random.Random(seed)
        ops = [">", ">=", "<", "<=", "==", "!="]
        fields = [f"f{i}" for i in range(6)]

        rules = [
            _leaf(rid, rng.choice(fields), rng.choice(ops), rng.randint(0, 100))
            for rid in range(1, 81)
        ]
        engines = _full_set_engines(rules)

        for _ in range(30):
            facts = {
                f: rng.randint(0, 100)
                for f in fields
                if rng.random() < 0.6  # sparse: some fields absent
            }
            _assert_full_set_agreement(rules, engines, facts)

    @pytest.mark.parametrize("seed", list(range(5)))
    def test_random_composite_rulesets(self, seed: int):
        rng = random.Random(1000 + seed)
        ops = [">", "<", "==", "!="]
        fields = [f"f{i}" for i in range(5)]

        def rand_leaf() -> dict:
            return {
                "type": "condition",
                "field": rng.choice(fields),
                "op": rng.choice(ops),
                "value": rng.randint(0, 50),
            }

        rules: list[Rule] = []
        for rid in range(1, 51):
            kind = rng.choice(["leaf", "and", "or"])
            if kind == "leaf":
                rules.append(_leaf(rid, rng.choice(fields), rng.choice(ops), rng.randint(0, 50)))
            elif kind == "and":
                rules.append(_and(rid, [rand_leaf() for _ in range(rng.randint(2, 3))]))
            else:
                rules.append(_or(rid, [rand_leaf() for _ in range(rng.randint(2, 3))]))

        engines = _full_set_engines(rules)
        for _ in range(30):
            facts = {f: rng.randint(0, 50) for f in fields if rng.random() < 0.7}
            _assert_full_set_agreement(rules, engines, facts)


# Streaming delta contract (documented optimization, verified explicitly)


class TestStreamingDeltaContract:
    def test_first_sight_matches_stateless_then_repeat_is_empty(self):
        rules = [
            _leaf(1, "temp", ">", 70),
            _leaf(2, "temp", "<", 60),
            _and(
                3,
                [
                    {"type": "condition", "field": "temp", "op": ">", "value": 65},
                    {"type": "condition", "field": "humidity", "op": ">", "value": 50},
                ],
            ),
        ]
        stateless = _fresh_stateless(rules)
        streaming = _fresh_streaming(rules)

        facts = {"temp": 72, "humidity": 55}
        # First sight: streaming delta == stateless full set.
        assert _fired_set(streaming, facts) == _fired_set(stateless, facts)

        # Exact repeats: streaming reports an empty delta (nothing changed).
        assert _fired_set(streaming, facts) == set()
        assert _fired_set(streaming, facts) == set()

    def test_changed_fact_re_reports_full_set(self):
        rules = [
            _leaf(1, "temp", ">", 70),
            _leaf(2, "temp", "<", 60),
        ]
        stateless = _fresh_stateless(rules)
        streaming = _fresh_streaming(rules)

        f1 = {"temp": 72}
        f2 = {"temp": 55}

        assert _fired_set(streaming, f1) == _fired_set(stateless, f1)
        # Change the fact: streaming re-evaluates affected rules and must match
        # the stateless full set for the new fact state.
        assert _fired_set(streaming, f2) == _fired_set(stateless, f2)
