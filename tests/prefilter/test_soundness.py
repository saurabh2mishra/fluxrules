"""Pre-filter correctness gate.

The single most important property: the pre-filter must be **sound** - it may
return extra candidate facts (false positives), but it must NEVER drop a fact
that would actually fire a rule (no false negatives).

These tests build random rule sets + random facts, evaluate every fact with the
real engine, and assert that every fact which fires ≥1 rule survives the
pre-filter.
"""

from __future__ import annotations

import random

import pytest

from fluxrules import Rule
from fluxrules.engine.phreak import PhreakEngine
from fluxrules.prefilter import (
    FactPreFilterStore,
    PredicateExtractor,
    PreFilteredEvaluator,
)

OPS = [">", ">=", "<", "<=", "=="]


def _leaf(field: str, op: str, value: int) -> dict:
    return {"type": "condition", "field": field, "op": op, "value": value}


def _and_rule(rid: int, n_conditions: int, n_fields: int) -> Rule:
    fields = random.sample(range(n_fields), min(n_conditions, n_fields))
    conditions = [_leaf(f"field_{f}", random.choice(OPS), random.randint(0, 1000)) for f in fields]
    dsl = conditions[0] if len(conditions) == 1 else {"type": "and", "conditions": conditions}
    return Rule(id=rid, name=f"r{rid}", condition_dsl=dsl, priority=rid % 5, persist=False)


def _or_rule(rid: int, n_fields: int) -> Rule:
    branches = [
        _leaf(
            f"field_{random.randint(0, n_fields - 1)}",
            random.choice(OPS),
            random.randint(0, 1000),
        )
        for _ in range(random.randint(2, 3))
    ]
    return Rule(
        id=rid,
        name=f"r{rid}",
        condition_dsl={"type": "or", "conditions": branches},
        persist=False,
    )


def _random_fact(n_fields: int, density: float) -> dict:
    fact = {}
    for i in range(n_fields):
        if random.random() < density:
            fact[f"field_{i}"] = random.randint(0, 1000)
    return fact


def _sqlite_store(tmp_path) -> FactPreFilterStore:
    from sqlalchemy import create_engine

    engine = create_engine(f"sqlite:///{tmp_path}/prefilter_test.db", future=True)
    return FactPreFilterStore(engine=engine)


@pytest.mark.parametrize("seed", [1, 7, 42, 1234])
def test_prefilter_is_sound_and_rules(tmp_path, seed):
    """No fact that fires a rule may be dropped by the pre-filter (AND rules)."""
    random.seed(seed)
    n_fields = 20
    rules = [_and_rule(i, random.randint(1, 4), n_fields) for i in range(200)]
    facts = [_random_fact(n_fields, density=0.7) for _ in range(2_000)]

    engine = PhreakEngine(streaming_mode=False)
    engine.load_rules(rules)

    # Ground truth: which facts actually fire ≥1 rule.
    firing = [i for i, f in enumerate(facts) if engine.evaluate(f).fired_rules]

    store = _sqlite_store(tmp_path)
    evaluator = PreFilteredEvaluator(engine=engine, store=store)
    candidates = list(evaluator.iter_candidates(facts))
    candidate_keys = {frozenset(c.items()) for c in candidates}

    # Every firing fact MUST appear among candidates.
    for i in firing:
        key = frozenset(facts[i].items())
        assert key in candidate_keys, f"fact {i} fires a rule but was dropped: {facts[i]}"

    store.dispose()


@pytest.mark.parametrize("seed", [2, 99])
def test_prefilter_is_sound_or_rules(tmp_path, seed):
    """OR rules must also be sound (field necessary only if in every branch)."""
    random.seed(seed)
    n_fields = 15
    rules = [_or_rule(i, n_fields) for i in range(120)]
    facts = [_random_fact(n_fields, density=0.6) for _ in range(1_500)]

    engine = PhreakEngine(streaming_mode=False)
    engine.load_rules(rules)
    firing = [i for i, f in enumerate(facts) if engine.evaluate(f).fired_rules]

    store = _sqlite_store(tmp_path)
    candidates = list(PreFilteredEvaluator(engine=engine, store=store).iter_candidates(facts))
    candidate_keys = {frozenset(c.items()) for c in candidates}

    for i in firing:
        assert frozenset(facts[i].items()) in candidate_keys
    store.dispose()


def test_prefilter_actually_reduces(tmp_path):
    """Selective AND rules should eliminate a large fraction of facts."""
    random.seed(5)
    n_fields = 50
    # Highly selective: each rule needs 5 narrow conditions.
    rules = []
    for i in range(300):
        fields = random.sample(range(n_fields), 5)
        conds = [_leaf(f"field_{f}", ">", 950) for f in fields]  # value>950 is rare
        rules.append(
            Rule(
                id=i,
                name=f"r{i}",
                condition_dsl={"type": "and", "conditions": conds},
                persist=False,
            )
        )

    facts = [_random_fact(n_fields, density=0.8) for _ in range(3_000)]
    engine = PhreakEngine(streaming_mode=False)
    engine.load_rules(rules)

    store = _sqlite_store(tmp_path)
    _, stats = PreFilteredEvaluator(engine=engine, store=store).run(facts)

    # Soundness still holds (run() evaluates candidates; firing facts ⊆ candidates
    # is guaranteed by construction). Assert meaningful reduction.
    assert stats.reduction_ratio > 0.5, f"weak reduction: {stats.reduction_ratio:.2%}"
    assert stats.candidate_facts <= stats.total_facts
    store.dispose()


def test_unfilterable_rule_falls_back_to_passthrough(tmp_path):
    """A NOT/custom rule forces a sound pass-through (all facts are candidates)."""
    random.seed(11)
    n_fields = 10
    rules = [
        Rule(
            id=1,
            name="not_rule",
            condition_dsl={"type": "not", "condition": _leaf("field_0", ">", 500)},
            persist=False,
        ),
        Rule(id=2, name="ok", condition_dsl=_leaf("field_1", ">", 900), persist=False),
    ]
    facts = [_random_fact(n_fields, density=0.9) for _ in range(500)]

    engine = PhreakEngine(streaming_mode=False)
    engine.load_rules(rules)

    preds = PredicateExtractor().from_rules(rules)
    assert preds.has_unfilterable_rule is True

    store = _sqlite_store(tmp_path)
    candidates = list(PreFilteredEvaluator(engine=engine, store=store).iter_candidates(facts))
    # Pass-through: every fact is a candidate (sound, no speedup).
    assert len(candidates) == len(facts)
    store.dispose()
