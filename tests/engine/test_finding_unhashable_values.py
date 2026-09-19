"""Regression tests: PHREAK handles unhashable values (was findings F3/F4).

Differential/battery testing surfaced two places where PHREAK raised
``TypeError: unhashable type`` on rules the reference oracle evaluated cleanly.
Both are now fixed; these tests lock the correct behavior forever.

F3 -- streaming on a list-valued FACT
    ``roles contains "admin"`` with ``roles = ["admin", "user"]`` matches in
    PHREAK stateless, PHREAK streaming, and the oracle. Streaming no longer
    crashes memoizing the unhashable list fact value (it skips the memo).

F4 -- a list-valued ``==`` RULE value
    A rule ``x == [1, 2]`` loads in both modes and matches ``x == [1, 2]`` (the
    alpha index keeps the field unconstrained rather than crashing).
"""

from __future__ import annotations

from fluxrules import Rule
from fluxrules.domain.models import Ruleset
from fluxrules.engine.phreak import PhreakEngine
from fluxrules.services.reference_evaluator import ReferenceEvaluator


def _oracle(rule: Rule, facts: dict) -> list[int]:
    ref = ReferenceEvaluator()
    ruleset = Ruleset(group="finding", rules=(rule.to_engine_rule(),))
    return ref.evaluate(ruleset, facts).matched_rule_ids


def test_f3_streaming_handles_list_valued_fact() -> None:
    """Regression (was F3): streaming matches a list-valued fact without crashing."""
    rule = Rule(
        id=1,
        name="roles_contains_admin",
        condition_dsl={"type": "condition", "field": "roles", "op": "contains", "value": "admin"},
        action="grant",
        persist=False,
    )
    facts = {"roles": ["admin", "user"]}

    assert _oracle(rule, facts) == [1]
    stateless = PhreakEngine(streaming_mode=False)
    stateless.load_rules([rule])
    assert stateless.evaluate(facts).fired_rules == [1]

    streaming = PhreakEngine(streaming_mode=True)
    streaming.load_rules([rule])
    assert streaming.evaluate(facts).fired_rules == [1]
    # A non-matching list fact must not fire.
    assert streaming.evaluate({"roles": ["user"]}).fired_rules == []


def test_f4_list_valued_eq_rule_value_loads_and_matches() -> None:
    """Regression (was F4): a list-valued ``==`` rule loads and matches in both modes."""
    rule = Rule(
        id=1,
        name="x_eq_list",
        condition_dsl={"type": "condition", "field": "x", "op": "==", "value": [1, 2]},
        action="a",
        persist=False,
    )

    assert _oracle(rule, {"x": [1, 2]}) == [1]
    for streaming_mode in (False, True):
        engine = PhreakEngine(streaming_mode=streaming_mode)
        engine.load_rules([rule])
        assert engine.evaluate({"x": [1, 2]}).fired_rules == [1]
        assert engine.evaluate({"x": [3, 4]}).fired_rules == []
