"""Stronger stateless/streaming parity: ordered output, null handling, strict configs.

Audit 04 (H1/H2) noted the principal equivalence suite compared fired *sets*
only, and that null/tie/config divergence was a risk. FluxRules ships a single
engine (PHREAK), but it runs two evaluation paths that must agree: the
*stateless* path (full re-evaluation each call) and the *streaming* path
(delta-driven, first sight of a fact reports the full fired set). These tests
pin that the two paths never diverge:

* **Ordered** fired-rule parity (not just set parity), including priority order.
* **Null / missing** field parity under default and strict null handling.
* **Strict type comparison** parity.

A fresh streaming engine seeing a fact for the first time must produce the same
ordered output as the stateless engine; identical output across both paths is a
meaningful internal oracle.
"""

from __future__ import annotations

import pytest

from fluxrules import Rule
from fluxrules.engine.configuration import EngineConfig
from fluxrules.engine.phreak import PhreakEngine


def _leaf(rid, field, op, value, priority=0):
    return Rule(
        id=rid,
        name=f"rule_{rid}",
        condition_dsl={"type": "condition", "field": field, "op": op, "value": value},
        priority=priority,
        persist=False,
    )


def _both(rules, **cfg):
    config = EngineConfig(**cfg) if cfg else None
    stateless = PhreakEngine(config=config, streaming_mode=False)
    stateless.load_rules(rules)
    streaming = PhreakEngine(config=config, streaming_mode=True)
    streaming.load_rules(rules)
    return stateless, streaming


def test_ordered_fired_rules_match_by_priority():
    rules = [
        _leaf(1, "amount", ">", 100, priority=1),
        _leaf(2, "amount", ">", 100, priority=5),
        _leaf(3, "amount", ">", 100, priority=3),
    ]
    stateless, streaming = _both(rules)
    facts = {"amount": 500}
    p = stateless.evaluate(facts).fired_rules
    r = streaming.evaluate(facts).fired_rules
    # Same ordered output across both evaluation paths.
    assert p == r
    # Highest priority first (descending priority is the documented order).
    assert p[0] == 2


@pytest.mark.parametrize(
    "facts",
    [
        {"x": None},
        {},  # x absent
        {"x": 0},
        {"x": 5},
    ],
)
def test_null_and_missing_parity_default(facts):
    rules = [
        _leaf(1, "x", "==", None),
        _leaf(2, "x", "!=", 5),
        _leaf(3, "x", ">", 0),
    ]
    stateless, streaming = _both(rules)
    assert stateless.evaluate(facts).fired_rules == streaming.evaluate(facts).fired_rules


@pytest.mark.parametrize("facts", [{"x": None}, {}, {"x": 5}])
def test_null_parity_strict_null_handling(facts):
    rules = [_leaf(1, "x", "==", None), _leaf(2, "x", "!=", 5)]
    stateless, streaming = _both(rules, strict_null_handling=True)
    assert stateless.evaluate(facts).fired_rules == streaming.evaluate(facts).fired_rules


@pytest.mark.parametrize(
    "facts",
    [{"x": 5}, {"x": True}, {"x": 5.0}, {"x": 2}],
)
def test_strict_type_comparison_parity(facts):
    rules = [_leaf(1, "x", "==", 5), _leaf(2, "x", ">", 3)]
    stateless, streaming = _both(rules, strict_type_comparison=True)
    assert stateless.evaluate(facts).fired_rules == streaming.evaluate(facts).fired_rules
