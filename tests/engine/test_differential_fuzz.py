"""Differential correctness fuzz: PHREAK stateless == PHREAK streaming == oracle.

This is the highest-leverage correctness proof in the suite. Instead of a
handful of curated rules, it generates many random rulesets (leaf / ``and`` /
``or`` / ``not`` DSL, the full numeric operator set) and asserts, for every
generated fact, that the fired-rule **set** agrees across three evaluation
paths:

- ``PhreakEngine`` stateless (default),
- a *fresh* ``PhreakEngine(streaming_mode=True)`` (first sight of the fact),
- ``ReferenceEvaluator`` -- the dependency-free single-fact oracle and the
  source of truth for single-fact semantics.

## One proof across regimes

Full three-way equality is asserted over rulesets whose referenced fields are
**present** in the fact AND over rulesets where fields may be **absent** (which
exercises negation over missing data). Both hold: PHREAK stateless, PHREAK
streaming (fresh per fact), and the oracle fire exactly the same set.

Determinism: every ruleset/fact is seeded. The example budget is env-tunable via
``FLUXRULES_FUZZ_EXAMPLES`` so the fast ``-m "not performance"`` gate stays quick
while a nightly/opt-in run does a deeper sweep.
"""

from __future__ import annotations

import os
import random

import pytest

from fluxrules import Rule
from fluxrules.domain.models import Ruleset
from fluxrules.engine.phreak import PhreakEngine
from fluxrules.services.reference_evaluator import ReferenceEvaluator

_NUM_OPS = (">", ">=", "<", "<=", "==", "!=")
_FIELD_SPACE = 5
_VALUE_SPACE = 10
_EXAMPLES = int(os.environ.get("FLUXRULES_FUZZ_EXAMPLES", "400"))


def _condition(rng: random.Random) -> dict:
    return {
        "type": "condition",
        "field": f"f{rng.randint(0, _FIELD_SPACE - 1)}",
        "op": rng.choice(_NUM_OPS),
        "value": rng.randint(0, _VALUE_SPACE),
    }


def _dsl(rng: random.Random) -> dict:
    kind = rng.choice(("condition", "and", "or", "not"))
    if kind == "condition":
        return _condition(rng)
    if kind == "not":
        return {"type": "not", "conditions": [_condition(rng)]}
    n = rng.randint(1, 3)
    return {"type": kind, "conditions": [_condition(rng) for _ in range(n)]}


def _rule(rid: int, rng: random.Random) -> Rule:
    return Rule(
        id=rid,
        name=f"rule_{rid}",
        condition_dsl=_dsl(rng),
        action=f"action_{rid}",
        priority=rng.randint(0, 4),
        domain=f"d{rid % 3}",
        tags=frozenset([f"t{rid % 2}"]),
        persist=False,
    )


def _always_false_rule(rid: int) -> Rule:
    # A leaf whose value can never be met by the generated facts (which live in
    # 0.._VALUE_SPACE); adding it must never change any other rule's outcome.
    return Rule(
        id=rid,
        name=f"never_{rid}",
        condition_dsl={"type": "condition", "field": "f0", "op": ">", "value": _VALUE_SPACE + 5},
        action=f"never_{rid}",
        priority=0,
        persist=False,
    )


def _rules(seed: int) -> list[Rule]:
    rng = random.Random(seed)
    n = rng.randint(1, 8)
    return [_rule(i + 1, rng) for i in range(n)]


def _facts_present(seed: int) -> dict[str, int]:
    # Every field the rules can reference is present.
    rng = random.Random(seed ^ 0x5EED)
    return {f"f{i}": rng.randint(0, _VALUE_SPACE) for i in range(_FIELD_SPACE)}


def _facts_absent(seed: int) -> dict[str, int]:
    # Some fields intentionally omitted so absent-field paths are exercised.
    rng = random.Random(seed ^ 0x5EED)
    return {
        f"f{i}": rng.randint(0, _VALUE_SPACE) for i in range(_FIELD_SPACE) if rng.random() < 0.7
    }


def _stateless_fired(rules: list[Rule], facts: dict) -> list[int]:
    eng = PhreakEngine(streaming_mode=False)
    eng.load_rules(rules)
    return eng.evaluate(facts).fired_rules


def _streaming_fired_fresh(rules: list[Rule], facts: dict) -> list[int]:
    eng = PhreakEngine(streaming_mode=True)
    eng.load_rules(rules)
    return eng.evaluate(facts).fired_rules


def _oracle_matched(rules: list[Rule], facts: dict) -> list[int]:
    ref = ReferenceEvaluator()
    ruleset = Ruleset(group="fuzz", rules=tuple(r.to_engine_rule() for r in rules))
    return ref.evaluate(ruleset, facts).matched_rule_ids


def _assert_priority_major(fired: list[int], rules: list[Rule]) -> None:
    priority = {r.id: r.priority for r in rules}
    priorities = [priority[i] for i in fired]
    assert priorities == sorted(priorities, reverse=True), (
        f"fired rules not in non-increasing priority order: {list(zip(fired, priorities))}"
    )


@pytest.mark.parametrize("seed", range(_EXAMPLES))
def test_stateless_streaming_oracle_set_equality(seed: int) -> None:
    """Present-field regime: all three evaluators fire exactly the same set."""
    rules = _rules(seed)
    facts = _facts_present(seed)

    stateless = _stateless_fired(rules, facts)
    streaming = _streaming_fired_fresh(rules, facts)
    oracle = _oracle_matched(rules, facts)

    assert set(stateless) == set(oracle), (
        f"seed={seed}: PHREAK stateless {stateless} != oracle {oracle}"
    )
    assert set(streaming) == set(oracle), (
        f"seed={seed}: PHREAK streaming {streaming} != oracle {oracle}"
    )
    _assert_priority_major(stateless, rules)
    _assert_priority_major(streaming, rules)


@pytest.mark.parametrize("seed", range(_EXAMPLES))
def test_stateless_streaming_oracle_set_equality_with_absent_fields(seed: int) -> None:
    """Absent-field regime: all three evaluators still fire the same set.

    This exercises negation over missing fields (a NOT whose field is absent
    fires). PHREAK stateless, PHREAK streaming, and the oracle must agree.
    """
    rules = _rules(seed)
    facts = _facts_absent(seed)
    stateless = _stateless_fired(rules, facts)
    streaming = _streaming_fired_fresh(rules, facts)
    oracle = _oracle_matched(rules, facts)
    assert set(stateless) == set(oracle), (
        f"seed={seed}: PHREAK stateless {stateless} != oracle {oracle} (absent-field)"
    )
    assert set(streaming) == set(oracle), (
        f"seed={seed}: PHREAK streaming {streaming} != oracle {oracle} (absent-field)"
    )


@pytest.mark.parametrize("seed", range(_EXAMPLES))
def test_adding_non_matching_rule_changes_nothing(seed: int) -> None:
    rules = _rules(seed)
    facts = _facts_present(seed)
    base = set(_stateless_fired(rules, facts))

    extra_id = max((r.id for r in rules), default=0) + 1
    after = set(_stateless_fired([*rules, _always_false_rule(extra_id)], facts))

    assert extra_id not in after, f"seed={seed}: an always-false rule fired"
    assert after == base, f"seed={seed}: adding a non-matching rule changed {base ^ after}"


@pytest.mark.parametrize("seed", range(_EXAMPLES))
def test_rule_load_order_does_not_change_fired_set(seed: int) -> None:
    """Metamorphic: shuffling rule load order never changes *which* rules fire.

    (The intra-priority *order* may change -- finding F2 -- but the fired set is
    invariant.)
    """
    rules = _rules(seed)
    facts = _facts_present(seed)
    base = set(_stateless_fired(rules, facts))

    shuffled = list(rules)
    random.Random(seed ^ 0xABCD).shuffle(shuffled)
    assert set(_stateless_fired(shuffled, facts)) == base, (
        f"seed={seed}: load order changed the fired set"
    )


@pytest.mark.parametrize("seed", range(min(_EXAMPLES, 200)))
def test_streaming_same_fact_reports_empty_delta(seed: int) -> None:
    rules = _rules(seed)
    facts = _facts_present(seed)
    eng = PhreakEngine(streaming_mode=True)
    eng.load_rules(rules)

    first = eng.evaluate(facts).fired_rules
    second = eng.evaluate(dict(facts)).fired_rules

    assert set(first) == set(_oracle_matched(rules, facts))
    assert second == [], f"seed={seed}: streaming re-eval of same fact was not an empty delta"


def test_negation_over_absent_field_fires() -> None:
    """Regression (was finding F1): NOT over an absent field fires in all engines.

    A rule ``NOT(field == v)`` whose ``field`` is absent from the fact fires in
    the oracle (inner condition is False, so its negation is True) and now fires
    in PHREAK stateless and streaming as well -- including with an entirely empty
    fact. This is the minimal seed that exposed the original divergence; it is
    kept forever.
    """
    rule = Rule(
        id=1,
        name="not_absent",
        condition_dsl={
            "type": "not",
            "conditions": [{"type": "condition", "field": "missing", "op": "==", "value": 1}],
        },
        action="a",
        persist=False,
    )
    oracle = ReferenceEvaluator()
    ruleset = Ruleset(group="f1", rules=(rule.to_engine_rule(),))

    for facts in ({}, {"missing": 5}, {"other": 9}):
        assert oracle.evaluate(ruleset, facts).matched_rule_ids == [1]
        stateless = PhreakEngine(streaming_mode=False)
        stateless.load_rules([rule])
        assert stateless.evaluate(facts).fired_rules == [1], f"stateless missed NOT on {facts}"
        streaming = PhreakEngine(streaming_mode=True)
        streaming.load_rules([rule])
        assert streaming.evaluate(facts).fired_rules == [1], f"streaming missed NOT on {facts}"

    # Present field that satisfies the inner condition: must NOT fire.
    stateless = PhreakEngine(streaming_mode=False)
    stateless.load_rules([rule])
    assert stateless.evaluate({"missing": 1}).fired_rules == []


def test_hypothesis_differential_when_available() -> None:
    """Property-based variant with shrinking; runs in CI where hypothesis installs.

    Skips cleanly in offline/dev environments without hypothesis. The seeded
    parametrized tests above provide the always-on proof; this adds shrinking.
    Scoped to the present-field regime (see finding F1).
    """
    pytest.importorskip("hypothesis")
    from hypothesis import HealthCheck, given, settings
    from hypothesis import strategies as st

    @st.composite
    def rulesets(draw):
        n = draw(st.integers(min_value=1, max_value=6))
        rules = []
        for i in range(n):
            op = draw(st.sampled_from(_NUM_OPS))
            field = f"f{draw(st.integers(min_value=0, max_value=_FIELD_SPACE - 1))}"
            value = draw(st.integers(min_value=0, max_value=_VALUE_SPACE))
            kind = draw(st.sampled_from(("condition", "and", "or", "not")))
            leaf = {"type": "condition", "field": field, "op": op, "value": value}
            if kind == "condition":
                dsl = leaf
            elif kind == "not":
                dsl = {"type": "not", "conditions": [leaf]}
            else:
                dsl = {"type": kind, "conditions": [leaf]}
            rules.append(
                Rule(
                    id=i + 1,
                    name=f"r{i + 1}",
                    condition_dsl=dsl,
                    action=f"a{i + 1}",
                    priority=draw(st.integers(min_value=0, max_value=4)),
                    persist=False,
                )
            )
        facts = {
            f"f{i}": draw(st.integers(min_value=0, max_value=_VALUE_SPACE))
            for i in range(_FIELD_SPACE)
        }
        return rules, facts

    @settings(max_examples=_EXAMPLES, deadline=None, suppress_health_check=list(HealthCheck))
    @given(rulesets())
    def _check(payload):
        rules, facts = payload
        stateless = set(_stateless_fired(rules, facts))
        streaming = set(_streaming_fired_fresh(rules, facts))
        oracle = set(_oracle_matched(rules, facts))
        assert stateless == oracle == streaming

    _check()
