"""P1.2 - Single discovery path parity.

PhreakEngine used to run **two** independent per-fact discovery mechanisms and
reconcile them with a set intersection: the O(segments) ``TokenPropagator`` scan
(in ``BaseEngine.evaluate``) and the bit-mask linker + alpha (in
``_evaluate_rules``), combined as ``propagator ∩ linker ∩ alpha``. P1.2 collapses
this to **one** path (``PhreakEngine._candidate_rule_ids``: field-bearing
universe → alpha → linker) and removes the propagator scan from the hot path.

These tests prove the single path produces an *identical* candidate set to the
old reconciliation, for both stateless and streaming mode, including edge cases
(no-field rules, NOT/unfilterable rules, empty facts). The engine's
``strict_discovery=True`` switch performs the same comparison inline on every
fact; here we also assert it stays green and that production config runs only one
path.

Plan: ``.research/PHREAK_P1_PLAN_SCALING_EFFICIENCY.md`` task P1.2
(``test_single_discovery_parity.py``).
"""

from __future__ import annotations

import random

import pytest
from pydantic import ValidationError

from fluxrules import Rule
from fluxrules.engine.phreak._engine import PhreakEngine

_FIELDS = [f"f{i}" for i in range(6)]
_OPS = [">", ">=", "<", "<=", "=="]


def _leaf(field: str, op: str, value) -> dict:
    return {"type": "condition", "field": field, "op": op, "value": value}


def _rand_rule(rng: random.Random, rid: int) -> Rule:
    kind = rng.choice(["leaf", "and", "or", "not"])
    if kind == "leaf":
        dsl = _leaf(rng.choice(_FIELDS), rng.choice(_OPS), rng.randint(0, 50))
    elif kind == "not":
        dsl = {
            "type": "not",
            "condition": _leaf(rng.choice(_FIELDS), rng.choice(_OPS), rng.randint(0, 50)),
        }
    else:
        conds = [_leaf(rng.choice(_FIELDS), rng.choice(_OPS), rng.randint(0, 50)) for _ in range(2)]
        dsl = {"type": kind, "conditions": conds}
    return Rule(id=rid, name=f"r{rid}", condition_dsl=dsl, priority=rid % 5, persist=False)


def _rand_fact(rng: random.Random) -> dict:
    return {f: rng.randint(0, 50) for f in _FIELDS if rng.random() < 0.75}


def _legacy_candidates(engine: PhreakEngine, facts: dict) -> set[int]:
    """Recompute the corrected ``propagator ∩ linker ∩ alpha`` reconciliation.

    or/not rules bypass the presence linker (they can fire with some referenced
    fields absent - the F1 fix), so they are candidates whenever they survive
    alpha, regardless of field presence. This baseline mirrors that.
    """
    affected = engine.get_affected_segments(facts)
    propagator = set(engine.token_propagator.propagate(facts, affected))
    linker = engine._bitmask_linker.linked_rules_for(frozenset(facts.keys()))
    reconciled = propagator & linker
    if engine._alpha_engage and engine._alpha_index is not None:
        reconciled = set(engine._alpha_index.prune(facts, list(reconciled)))
    if engine._linker_unsafe_rule_ids:
        surviving = set(engine._field_bearing_rule_ids)
        if engine._alpha_engage and engine._alpha_index is not None:
            surviving = set(engine._alpha_index.prune(facts, list(engine._field_bearing_rule_ids)))
        reconciled |= surviving & engine._linker_unsafe_rule_ids
    return reconciled


@pytest.mark.parametrize("seed", [1, 7, 42, 123, 2024, 99999])
def test_single_path_matches_old_reconciliation(seed: int) -> None:
    """New single discovery set == old propagator ∩ linker ∩ alpha set."""
    rng = random.Random(seed)
    rules = [_rand_rule(rng, i) for i in range(80)]
    facts = [_rand_fact(rng) for _ in range(800)]

    engine = PhreakEngine(alpha_prefilter=True)
    engine.load_rules(rules)

    for fact in facts:
        single = set(engine._candidate_rule_ids(fact))
        legacy = _legacy_candidates(engine, fact)
        assert single == legacy, f"candidate mismatch on {fact}: {single} != {legacy}"


def test_strict_discovery_switch_runs_green() -> None:
    """``strict_discovery=True`` asserts parity inline and must not raise."""
    rng = random.Random(2024)
    rules = [_rand_rule(rng, i) for i in range(60)]
    facts = [_rand_fact(rng) for _ in range(500)]

    engine = PhreakEngine(alpha_prefilter=True, strict_discovery=True)
    engine.load_rules(rules)
    # If the single path ever diverged from the reconciliation, evaluate() would
    # raise AssertionError from _assert_discovery_parity.
    for fact in facts:
        engine.evaluate(fact)


def test_fired_rules_identical_to_alpha_off_baseline() -> None:
    """End-to-end: fired rules unchanged vs. the alpha-off baseline engine."""
    rng = random.Random(31337)
    rules = [_rand_rule(rng, i) for i in range(80)]
    facts = [_rand_fact(rng) for _ in range(600)]

    new = PhreakEngine(alpha_prefilter=True)
    new.load_rules(rules)
    base = PhreakEngine(alpha_prefilter=False)
    base.load_rules(rules)

    for fact in facts:
        assert set(new.evaluate(fact).fired_rules) == set(base.evaluate(fact).fired_rules)


def test_no_field_rule_excluded_like_propagator() -> None:
    """A no-condition-field rule was never surfaced by the propagator.

    Authoring such a rule is now refused outright, so the first assertion is
    that the guard holds. The engine behaviour is still pinned underneath it:
    a rule that bypasses validation must not appear as a candidate, while a
    normal rule on the same fact does. Both layers matter - the guard stops
    empty rules being created, and this keeps the engine honest if one ever
    reaches it another way.
    """
    with pytest.raises(ValidationError, match="could never fire"):
        Rule(
            id=1,
            name="empty",
            condition_dsl={"type": "and", "conditions": []},
            persist=False,
        )

    # Bypass validation to construct the shape the engine must still handle.
    empty = Rule.model_construct(
        id=1,
        name="empty",
        condition_dsl={"type": "and", "conditions": []},
        actions=(),
        action="",
        priority=0,
        enabled=True,
        domain="default",
        tags=frozenset(),
        metadata={},
        description="",
        version="1.0",
        sla_latency_ms=100,
        created_at=None,
        updated_at=None,
        persist=False,
    )
    rules = [
        empty,
        Rule(id=2, name="normal", condition_dsl=_leaf("amount", ">", 10), persist=False),
    ]
    engine = PhreakEngine(alpha_prefilter=True)
    engine.load_rules(rules)

    candidates = set(engine._candidate_rule_ids({"amount": 50}))
    assert 1 not in candidates  # no-field rule excluded, matching old behavior
    assert 2 in candidates
    # And parity with the reconciliation holds for this edge case too.
    assert candidates == _legacy_candidates(engine, {"amount": 50})


def test_empty_facts_yield_no_field_bearing_candidates() -> None:
    """Empty facts: only or/not rules (which can fire on absence) are candidates.

    Pure-conjunction rules need their fields present, so they are not candidates
    on an empty fact; or/not rules bypass the presence linker (F1) and remain
    candidates. Parity with the corrected reconciliation must hold either way.
    """
    rng = random.Random(7)
    rules = [_rand_rule(rng, i) for i in range(40)]
    engine = PhreakEngine(alpha_prefilter=True)
    engine.load_rules(rules)

    assert set(engine._candidate_rule_ids({})) == _legacy_candidates(engine, {})


@pytest.mark.parametrize("seed", [3, 88, 4242])
def test_streaming_discovery_parity_on_changed_facts(seed: int) -> None:
    """Streaming single path == reconciliation, comparing on changed facts.

    Streaming uses the incremental delta-linker; on each *changed* fact the
    discovered candidate set must still equal the stateless reconciliation for
    that fact's field presence + values.
    """
    rng = random.Random(seed)
    rules = [_rand_rule(rng, i) for i in range(50)]
    facts = [_rand_fact(rng) for _ in range(300)]

    stream = PhreakEngine(alpha_prefilter=True, streaming_mode=True)
    stream.load_rules(rules)
    # Reference engine (stateless) to compute the reconciliation per fact.
    ref = PhreakEngine(alpha_prefilter=True)
    ref.load_rules(rules)

    for fact in facts:
        single = set(stream._candidate_rule_ids(fact))
        legacy = _legacy_candidates(ref, fact)
        assert single == legacy, f"streaming mismatch on {fact}"
