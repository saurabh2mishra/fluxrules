"""P1.1 - Alpha-primary soundness parity.

The alpha pre-filter is now the *primary* per-fact candidate reducer (it runs
first, before the presence-only bit-mask linker, and is engaged by an adaptive
selectivity gate rather than a hardcoded rule-count threshold). It must remain an
*invisible* optimization: for **every** fact, the fired-rule set with alpha ON
must equal the set with alpha OFF. It may only make evaluation faster by skipping
rules that provably cannot fire - never drop a rule that would have fired.

This is the soundness gate for ``.research/PHREAK_P1_PLAN_SCALING_EFFICIENCY.md``
task P1.1 (``test_alpha_primary_soundness.py``).
"""

from __future__ import annotations

import random

import pytest

from fluxrules import Rule
from fluxrules.engine.phreak._engine import PhreakEngine

_FIELDS = [f"f{i}" for i in range(8)]
_OPS = [">", ">=", "<", "<=", "==", "in", "!="]


def _leaf(field: str, op: str, value) -> dict:
    return {"type": "condition", "field": field, "op": op, "value": value}


def _rand_leaf(rng: random.Random) -> dict:
    field = rng.choice(_FIELDS)
    op = rng.choice(_OPS)
    if op == "in":
        return _leaf(field, op, [rng.randint(0, 50) for _ in range(rng.randint(1, 4))])
    return _leaf(field, op, rng.randint(0, 50))


def _rand_rule(rng: random.Random, rid: int) -> Rule:
    kind = rng.choice(["leaf", "and", "or", "and3", "not", "nested"])
    if kind == "leaf":
        dsl = _rand_leaf(rng)
    elif kind == "and":
        dsl = {"type": "and", "conditions": [_rand_leaf(rng), _rand_leaf(rng)]}
    elif kind == "and3":
        dsl = {
            "type": "and",
            "conditions": [_rand_leaf(rng) for _ in range(3)],
        }
    elif kind == "or":
        dsl = {"type": "or", "conditions": [_rand_leaf(rng), _rand_leaf(rng)]}
    elif kind == "not":
        dsl = {"type": "not", "condition": _rand_leaf(rng)}
    else:  # nested AND-of-(OR, leaf)
        dsl = {
            "type": "and",
            "conditions": [
                {"type": "or", "conditions": [_rand_leaf(rng), _rand_leaf(rng)]},
                _rand_leaf(rng),
            ],
        }
    return Rule(id=rid, name=f"r{rid}", condition_dsl=dsl, priority=rid % 7, persist=False)


def _rand_fact(rng: random.Random) -> dict:
    # Each field present with 80% probability so both presence (linking) and
    # value (alpha) vary across facts; values overlap the rule thresholds.
    return {f: rng.randint(0, 50) for f in _FIELDS if rng.random() < 0.8}


@pytest.mark.parametrize("seed", [1, 13, 99, 2024, 7777, 42, 314159])
def test_alpha_on_equals_alpha_off_for_every_fact(seed: int) -> None:
    """Alpha-on fired set ≡ alpha-off fired set, per fact (no false negatives)."""
    rng = random.Random(seed)
    rules = [_rand_rule(rng, i) for i in range(120)]
    facts = [_rand_fact(rng) for _ in range(1200)]

    on = PhreakEngine(alpha_prefilter=True)
    on.load_rules(rules)
    off = PhreakEngine(alpha_prefilter=False)
    off.load_rules(rules)

    for fact in facts:
        got = set(on.evaluate(fact).fired_rules)
        expected = set(off.evaluate(fact).fired_rules)
        assert got == expected, f"divergence on {fact}: {got} != {expected}"


def test_alpha_primary_runs_before_linker_and_prunes() -> None:
    """A selective rule set: alpha (value-aware) must be the layer that prunes.

    Every fact carries the hot field, so the presence-only linker links *all*
    rules and prunes nothing. Only the value-aware alpha layer can reduce the
    candidate set - proving it is the primary reducer.
    """
    # 200 rules all keyed on the same hot field with distinct thresholds.
    rules = [
        Rule(id=i, name=f"r{i}", condition_dsl=_leaf("amount", ">", i * 5), persist=False)
        for i in range(200)
    ]
    engine = PhreakEngine(alpha_prefilter=True)
    engine.load_rules(rules)

    # A small amount fires only the few low-threshold rules; alpha must drop the
    # rest *before* per-rule evaluation.
    res = engine.evaluate({"amount": 12})
    expected = {i for i in range(200) if i * 5 < 12}  # i*5 < 12 -> i in {0,1,2}
    assert set(res.fired_rules) == expected

    stats = engine.get_prefilter_stats()
    assert stats["engaged"] is True
    # Alpha saw all 200 field-bearing candidates and cut them well below 200.
    assert stats["last_candidates_in"] == 200
    assert stats["last_candidates_out"] < 200
    assert stats["prune_ratio"] > 0.0


def test_alpha_parity_with_unfilterable_mixed_set() -> None:
    """NOT/unfilterable rules force pass-through but parity must still hold."""
    rng = random.Random(5)
    rules = [
        Rule(
            id=1,
            name="not_r",
            condition_dsl={"type": "not", "condition": _leaf("f0", "==", 1)},
            persist=False,
        ),
        Rule(id=2, name="r2", condition_dsl=_leaf("f1", ">", 40), persist=False),
        Rule(id=3, name="r3", condition_dsl=_leaf("f2", "<", 5), persist=False),
        Rule(
            id=4,
            name="r4",
            condition_dsl={
                "type": "and",
                "conditions": [_leaf("f1", ">", 10), _leaf("f3", "<", 30)],
            },
            persist=False,
        ),
    ]
    on = PhreakEngine(alpha_prefilter=True)
    on.load_rules(rules)
    off = PhreakEngine(alpha_prefilter=False)
    off.load_rules(rules)

    # Index is pass_through (rule 1 unfilterable) but can still prune rules 2-4.
    assert on._alpha_index is not None and on._alpha_index.pass_through is True
    for _ in range(800):
        fact = _rand_fact(rng)
        assert set(on.evaluate(fact).fired_rules) == set(off.evaluate(fact).fired_rules)
