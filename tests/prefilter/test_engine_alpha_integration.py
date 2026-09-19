"""Parity + reduction tests for the PhreakEngine alpha pre-filter.

The alpha pre-filter must be an *invisible* optimization: for any fact, the set
of fired rules with the pre-filter ON must equal the set with it OFF. It may only
make evaluation faster by skipping rules that could never fire.
"""

from __future__ import annotations

import random

import pytest

from fluxrules import Rule
from fluxrules.engine.phreak._engine import PhreakEngine


def _rule(rid: int, dsl: dict) -> Rule:
    return Rule(id=rid, name=f"r{rid}", condition_dsl=dsl, priority=rid % 5, persist=False)


def _leaf(field: str, op: str, value) -> dict:
    return {"type": "condition", "field": field, "op": op, "value": value}


_FIELDS = [f"f{i}" for i in range(6)]
_OPS = [">", ">=", "<", "<=", "=="]


def _rand_rule(rng: random.Random, rid: int) -> Rule:
    kind = rng.choice(["leaf", "and", "or"])
    if kind == "leaf":
        return _rule(rid, _leaf(rng.choice(_FIELDS), rng.choice(_OPS), rng.randint(0, 50)))
    conds = [_leaf(rng.choice(_FIELDS), rng.choice(_OPS), rng.randint(0, 50)) for _ in range(2)]
    return _rule(rid, {"type": kind, "conditions": conds})


def _rand_fact(rng: random.Random) -> dict:
    return {f: rng.randint(0, 50) for f in _FIELDS if rng.random() < 0.8}


@pytest.mark.parametrize("seed", [1, 13, 99, 2024, 7777])
def test_alpha_prefilter_fired_rules_parity(seed: int) -> None:
    rng = random.Random(seed)
    rules = [_rand_rule(rng, i) for i in range(40)]
    facts = [_rand_fact(rng) for _ in range(800)]

    on = PhreakEngine(alpha_prefilter=True)
    on.load_rules(rules)
    off = PhreakEngine(alpha_prefilter=False)
    off.load_rules(rules)

    for fact in facts:
        got = set(on.evaluate(fact).fired_rules)
        expected = set(off.evaluate(fact).fired_rules)
        assert got == expected, f"divergence on {fact}: {got} != {expected}"


def test_alpha_prefilter_handles_unfilterable_rules() -> None:
    # A NOT rule is unfilterable -> must always be considered; filterable rules
    # are still pruned. Parity must hold regardless.
    rng = random.Random(0)
    rules = [
        _rule(1, {"type": "not", "condition": _leaf("f0", "==", 1)}),
        _rule(2, _leaf("f1", ">", 40)),
        _rule(3, _leaf("f2", "<", 5)),
    ]
    on = PhreakEngine(alpha_prefilter=True)
    on.load_rules(rules)
    off = PhreakEngine(alpha_prefilter=False)
    off.load_rules(rules)

    assert on._alpha_index is not None and on._alpha_index.pass_through is True
    for _ in range(500):
        fact = _rand_fact(rng)
        assert set(on.evaluate(fact).fired_rules) == set(off.evaluate(fact).fired_rules)
