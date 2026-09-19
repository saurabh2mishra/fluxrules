"""Conflict-resolution ordering parity across PHREAK and the oracle.

Set-equality (which rules fire) is proven in ``test_differential_fuzz.py``. This
module pins *ordering* -- the sequence in which rules fire and therefore the
order in which their actions execute.

Both evaluators now emit fired rules in the same total order: **priority
descending, then rule id descending**. This includes the intra-priority
tiebreak, which is id-descending and independent of rule load order (was
finding F2, now fixed).
"""

from __future__ import annotations

import random

import pytest

from fluxrules import Rule
from fluxrules.domain.models import Ruleset
from fluxrules.engine.phreak import PhreakEngine
from fluxrules.services.reference_evaluator import ReferenceEvaluator


def _rule(rid: int, priority: int) -> Rule:
    # A leaf that always matches x > 0 for x >= 1, so every rule fires.
    return Rule(
        id=rid,
        name=f"rule_{rid}",
        condition_dsl={"type": "condition", "field": "x", "op": ">", "value": 0},
        action=f"action_{rid}",
        priority=priority,
        persist=False,
    )


def _priority_of(rules: list[Rule]) -> dict[int, int]:
    return {r.id: r.priority for r in rules}


@pytest.mark.parametrize("seed", range(200))
def test_fired_order_matches_oracle(seed: int) -> None:
    """PHREAK's fired sequence equals the oracle's (priority, id)-desc order."""
    rng = random.Random(seed)
    n = rng.randint(1, 10)
    rules = [_rule(i + 1, rng.randint(0, 3)) for i in range(n)]
    facts = {"x": 5}

    phreak = PhreakEngine()
    phreak.load_rules(rules)
    oracle = ReferenceEvaluator()
    ruleset = Ruleset(group="ord", rules=tuple(r.to_engine_rule() for r in rules))

    pf = phreak.evaluate(facts).fired_rules
    om = oracle.evaluate(ruleset, facts).matched_rule_ids
    prio = _priority_of(rules)

    for fired in (pf, om):
        priorities = [prio[i] for i in fired]
        assert priorities == sorted(priorities, reverse=True), (
            f"seed={seed}: {fired} not in non-increasing priority order"
        )
    # Full ordered equality, including the intra-priority id-desc tiebreak.
    assert pf == om, f"seed={seed}: PHREAK order {pf} != oracle order {om}"


def test_intra_priority_tiebreak_is_id_descending_and_load_order_independent() -> None:
    """Regression (was finding F2): equal-priority rules fire id-descending in both.

    Two rules with the SAME priority both fire. Both the oracle and PHREAK order
    them by id descending, regardless of the order the rules were loaded in, so
    action execution order now matches across evaluators.
    """
    oracle = ReferenceEvaluator()
    facts = {"x": 5}

    for load in ([_rule(1, 0), _rule(2, 0)], [_rule(2, 0), _rule(1, 0)]):
        phreak = PhreakEngine()
        phreak.load_rules(load)
        result = phreak.evaluate(facts)
        assert result.fired_rules == [2, 1], f"load {[r.id for r in load]} -> {result.fired_rules}"
        assert result.actions == ["action_2", "action_1"]

        ruleset = Ruleset(group="t", rules=tuple(r.to_engine_rule() for r in load))
        oracle_result = oracle.evaluate(ruleset, facts)
        assert oracle_result.matched_rule_ids == [2, 1]
        assert result.fired_rules == oracle_result.matched_rule_ids
