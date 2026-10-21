"""The alpha prefilter must not crash on values it cannot compare.

A fact value that Python cannot compare with a rule value (``"x" > 5``) or
cannot hash (a list tested with ``in``) raises ``TypeError`` inside the
prefilter's node test. The prefilter must treat that as "keep the candidate",
so the engine evaluates the rule and returns its normal answer. The result with
the prefilter on must equal the result with it off.
"""

from __future__ import annotations

import pytest

from fluxrules import F, Rule
from fluxrules.engine.phreak import PhreakEngine


def _fire(rules: list[Rule], fact: dict, *, alpha: bool) -> list[int]:
    engine = PhreakEngine(alpha_prefilter=alpha)
    engine.load_rules(rules)
    return engine.evaluate(fact).fired_rules


@pytest.mark.parametrize(
    ("case", "condition", "fact"),
    [
        ("> on a string", F("s") > 5, {"s": "x"}),
        (">= on a string", F("s") >= 5, {"s": "x"}),
        ("< on a dict", F("s") < 5, {"s": {"a": 1}}),
        ("<= on a dict", F("s") <= 5, {"s": {"a": 1}}),
        ("isin with a list value", F("s").isin(["NG"]), {"s": ["NG"]}),
        ("isin with a dict value", F("s").isin(["NG"]), {"s": {"c": "NG"}}),
    ],
)
def test_uncomparable_value_does_not_crash(case, condition, fact):
    rule = Rule(id=1, name="r", conditions=condition, action="a")
    assert _fire([rule], fact, alpha=True) == _fire([rule], fact, alpha=False) == []


def test_other_rules_still_prune_and_fire_when_one_value_is_uncomparable():
    # One node raises for this fact; the others must still be decided normally.
    rules = [
        Rule(id=1, name="uncomparable", conditions=F("s") > 5, action="a"),
        Rule(id=2, name="fires", conditions=F("n") > 5, action="b"),
        Rule(id=3, name="pruned", conditions=F("n") > 100, action="c"),
    ]
    fact = {"s": "x", "n": 9}
    assert _fire(rules, fact, alpha=True) == _fire(rules, fact, alpha=False) == [2]


def test_rule_still_fires_when_another_branch_matches():
    # OR keeps the rule a candidate; the comparable branch decides it.
    rule = Rule(id=1, name="r", conditions=(F("s") > 5) | (F("n") == 1), action="a")
    fact = {"s": "x", "n": 1}
    assert _fire([rule], fact, alpha=True) == _fire([rule], fact, alpha=False) == [1]
