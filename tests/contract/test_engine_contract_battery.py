"""Shared engine-contract battery, parametrized over every contract-claiming engine.

The original contract test exercised one engine (``ReferenceEvaluator``) with a
single rule and a single fact. This replaces it with one battery run against
**every** engine that claims the single-fact contract:

- ``ReferenceEvaluator`` (the oracle),
- ``PhreakEngine`` stateless,
- ``PhreakEngine(streaming_mode=True)`` (fresh per fact).

Each engine is reduced to a common shape -- ``fired_set(rules, facts) -> set[int]``
-- and must return the expected fired-rule set for every case. Cases use present
fields only, so the negation-over-absent-field divergence (finding F1) is out of
scope here; correctness of that construct is tracked in
``tests/engine/test_differential_fuzz.py``.
"""

from __future__ import annotations

import pytest

from fluxrules import Rule
from fluxrules.domain.models import Ruleset
from fluxrules.engine.phreak import PhreakEngine
from fluxrules.services.reference_evaluator import ReferenceEvaluator


def _reference_fired(rules: list[Rule], facts: dict) -> set[int]:
    ref = ReferenceEvaluator()
    ruleset = Ruleset(group="battery", rules=tuple(r.to_engine_rule() for r in rules))
    return set(ref.evaluate(ruleset, facts).matched_rule_ids)


def _phreak_stateless_fired(rules: list[Rule], facts: dict) -> set[int]:
    eng = PhreakEngine(streaming_mode=False)
    eng.load_rules(rules)
    return set(eng.evaluate(facts).fired_rules)


def _phreak_streaming_fired(rules: list[Rule], facts: dict) -> set[int]:
    eng = PhreakEngine(streaming_mode=True)
    eng.load_rules(rules)
    return set(eng.evaluate(facts).fired_rules)


ENGINES = {
    "reference": _reference_fired,
    "phreak_stateless": _phreak_stateless_fired,
    "phreak_streaming": _phreak_streaming_fired,
}


def _leaf(rid, field, op, value, priority=0):
    return Rule(
        id=rid,
        name=f"r{rid}",
        condition_dsl={"type": "condition", "field": field, "op": op, "value": value},
        action=f"a{rid}",
        priority=priority,
        persist=False,
    )


def _tree(rid, dsl, priority=0):
    return Rule(
        id=rid,
        name=f"r{rid}",
        condition_dsl=dsl,
        action=f"a{rid}",
        priority=priority,
        persist=False,
    )


_C = {"type": "condition"}


def _cond(field, op, value):
    return {**_C, "field": field, "op": op, "value": value}


# (id, rules, facts, expected_fired_ids)
_BATTERY = [
    ("leaf_match", [_leaf(1, "x", ">", 10)], {"x": 20}, {1}),
    ("leaf_no_match", [_leaf(1, "x", ">", 10)], {"x": 5}, set()),
    (
        "and_all_true",
        [_tree(1, {"type": "and", "conditions": [_cond("x", ">", 0), _cond("y", "<", 10)]})],
        {"x": 5, "y": 3},
        {1},
    ),
    (
        "and_one_false",
        [_tree(1, {"type": "and", "conditions": [_cond("x", ">", 0), _cond("y", "<", 10)]})],
        {"x": 5, "y": 50},
        set(),
    ),
    (
        "or_one_true",
        [_tree(1, {"type": "or", "conditions": [_cond("x", ">", 100), _cond("y", "==", 3)]})],
        {"x": 5, "y": 3},
        {1},
    ),
    (
        "not_present_true",
        [_tree(1, {"type": "not", "conditions": [_cond("x", "==", 1)]})],
        {"x": 2},
        {1},
    ),
    (
        "not_present_false",
        [_tree(1, {"type": "not", "conditions": [_cond("x", "==", 1)]})],
        {"x": 1},
        set(),
    ),
    ("in_operator", [_leaf(1, "country", "in", ["US", "CA"])], {"country": "CA"}, {1}),
    (
        "contains_operator",
        [_leaf(1, "roles", "contains", "admin")],
        {"roles": ["admin", "user"]},
        {1},
    ),
    (
        "multi_rule_multi_fire",
        [
            _leaf(1, "x", ">", 0, priority=2),
            _leaf(2, "x", "<", 100, priority=1),
            _leaf(3, "x", "==", 999),
        ],
        {"x": 42},
        {1, 2},
    ),
]


@pytest.mark.parametrize("engine_name", list(ENGINES))
@pytest.mark.parametrize("case", _BATTERY, ids=[c[0] for c in _BATTERY])
def test_engine_contract_battery(engine_name: str, case) -> None:
    _id, rules, facts, expected = case
    fired = ENGINES[engine_name](rules, facts)
    assert fired == expected, f"{engine_name} on {_id}: fired {fired}, expected {expected}"


@pytest.mark.parametrize("case", _BATTERY, ids=[c[0] for c in _BATTERY])
def test_all_engines_agree(case) -> None:
    """Cross-engine agreement: every contract engine returns the same set."""
    _id, rules, facts, _expected = case
    results = {name: fn(rules, facts) for name, fn in ENGINES.items()}
    assert len(set(map(frozenset, results.values()))) == 1, f"{_id}: engines disagree: {results}"
