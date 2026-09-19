"""Independent oracle + truth-maintenance properties for the cross-fact CrossFactEngine.

The single-fact ``ReferenceEvaluator`` cannot validate the beta (join) engine, so
until now ``CrossFactEngine`` had no oracle. This module supplies one: a naive,
dependency-free nested-loop evaluator that computes the exact set of activations
for pattern-only rules (alpha constraints + equality/comparison joins) by brute
force, and diffs it against ``CrossFactEngine`` over many seeded random fact sets.

It also pins the truth-maintenance invariants that make an incremental join
engine trustworthy:

- **insert -> retract restores**: retracting a just-inserted fact returns the
  activation set to exactly what it was before.
- **independent inserts commute**: order of inserting unrelated facts does not
  change the final activation set.
- **retract un-fires**: removing a joined fact removes its dependent activations.

Determinism: every fact set is seeded; the example budget is env-tunable via
``FLUXRULES_FUZZ_EXAMPLES``.
"""

from __future__ import annotations

import os
import random

import pytest

from fluxrules.engine.cross_fact import (
    AlphaConstraint,
    CrossFactEngine,
    CrossFactRule,
    JoinConstraint,
    Pattern,
)
from fluxrules.engine.operators import evaluate_operator

_EXAMPLES = int(os.environ.get("FLUXRULES_FUZZ_EXAMPLES", "200"))


def _op(op: str, left, right) -> bool:
    return evaluate_operator(
        op,
        left,
        right,
        field_present=left is not None,
        strict_null_handling=False,
        strict_type_comparison=False,
        boolean_string_coercion=False,
        emit_metrics=False,
    )


# --- rules under test ---------------------------------------------------------


def _big_order_gold_rule() -> CrossFactRule:
    return CrossFactRule(
        id=1,
        name="big-order-gold",
        patterns=[
            Pattern("o", "Order", constraints=[AlphaConstraint("amount", ">", 1000)]),
            Pattern(
                "c",
                "Customer",
                constraints=[AlphaConstraint("tier", "==", "gold")],
                joins=[JoinConstraint("id", "==", "o", "customer_id")],
            ),
        ],
    )


def _comparison_join_rule() -> CrossFactRule:
    # Non-equality join exercises the filtered-scan path: b.w must exceed a.v.
    return CrossFactRule(
        id=2,
        name="b-exceeds-a",
        patterns=[
            Pattern("a", "A", constraints=[AlphaConstraint("v", ">=", 0)]),
            Pattern("b", "B", joins=[JoinConstraint("w", ">", "a", "v")]),
        ],
    )


RULES = [_big_order_gold_rule(), _comparison_join_rule()]


# --- the naive oracle ---------------------------------------------------------


def _canon(fields: dict) -> tuple:
    return tuple(sorted(fields.items()))


def _oracle_activations(rules, facts_by_type: dict[str, list[dict]]) -> set:
    results: set = set()

    for rule in rules:
        patterns = rule.patterns

        def recurse(i: int, bound: dict[str, dict], _patterns=patterns, _rule=rule) -> None:
            if i == len(_patterns):
                key = (_rule.id, tuple(_canon(bound[p.var]) for p in _patterns))
                results.add(key)
                return
            p = _patterns[i]
            for fact in facts_by_type.get(p.fact_type, []):
                if not all(_op(c.op, fact.get(c.field), c.value) for c in p.constraints):
                    continue
                ok = True
                for j in p.joins:
                    other = bound[j.other_var]
                    if not _op(j.op, fact.get(j.this_field), other.get(j.other_field)):
                        ok = False
                        break
                if ok:
                    recurse(i + 1, {**bound, p.var: fact}, _patterns, _rule)

        recurse(0, {})
    return results


def _engine_activations(engine: CrossFactEngine, rules) -> set:
    by_rule = {r.id: [p.var for p in r.patterns] for r in rules}
    out: set = set()
    for act in engine.activations():
        variables = by_rule[act.rule_id]
        out.add((act.rule_id, tuple(_canon(act.bindings[v]) for v in variables)))
    return out


# --- fact generation ----------------------------------------------------------


def _random_facts(seed: int) -> dict[str, list[dict]]:
    rng = random.Random(seed)
    customers = [
        {"id": rng.randint(1, 5), "tier": rng.choice(["gold", "silver"])}
        for _ in range(rng.randint(0, 5))
    ]
    orders = [
        {"customer_id": rng.randint(1, 5), "amount": rng.randint(0, 3000)}
        for _ in range(rng.randint(0, 5))
    ]
    a_facts = [{"v": rng.randint(0, 10)} for _ in range(rng.randint(0, 4))]
    b_facts = [{"w": rng.randint(0, 10)} for _ in range(rng.randint(0, 4))]
    return {"Customer": customers, "Order": orders, "A": a_facts, "B": b_facts}


def _load_all(facts_by_type: dict[str, list[dict]]) -> CrossFactEngine:
    engine = CrossFactEngine()
    engine.load_rules(RULES)
    for fact_type, facts in facts_by_type.items():
        for fields in facts:
            engine.insert(fact_type, dict(fields))
    return engine


@pytest.mark.parametrize("seed", range(_EXAMPLES))
def test_beta_engine_matches_naive_oracle(seed: int) -> None:
    facts = _random_facts(seed)
    engine = _load_all(facts)
    assert _engine_activations(engine, RULES) == _oracle_activations(RULES, facts), (
        f"seed={seed}: CrossFactEngine and the nested-loop oracle disagreed"
    )


@pytest.mark.parametrize("seed", range(_EXAMPLES))
def test_insert_then_retract_restores_activation_set(seed: int) -> None:
    facts = _random_facts(seed)
    engine = _load_all(facts)
    before = _engine_activations(engine, RULES)

    # Insert one more joinable fact, then retract it: state must return exactly.
    handle = engine.insert("Order", {"customer_id": 3, "amount": 2500}).handle
    engine.retract(handle.id)

    assert _engine_activations(engine, RULES) == before, (
        f"seed={seed}: insert->retract did not restore the prior activation set"
    )


@pytest.mark.parametrize("seed", range(min(_EXAMPLES, 100)))
def test_independent_inserts_commute(seed: int) -> None:
    rng = random.Random(seed ^ 0xC0FFEE)
    cust = {"id": rng.randint(1, 5), "tier": rng.choice(["gold", "silver"])}
    order = {"customer_id": rng.randint(1, 5), "amount": rng.randint(0, 3000)}

    e1 = CrossFactEngine()
    e1.load_rules(RULES)
    e1.insert("Customer", dict(cust))
    e1.insert("Order", dict(order))

    e2 = CrossFactEngine()
    e2.load_rules(RULES)
    e2.insert("Order", dict(order))
    e2.insert("Customer", dict(cust))

    assert _engine_activations(e1, RULES) == _engine_activations(e2, RULES), (
        f"seed={seed}: insertion order changed the final activation set"
    )


def test_retract_joined_fact_unfires_dependent_activation() -> None:
    engine = CrossFactEngine()
    engine.load_rules(RULES)
    cust = engine.insert("Customer", {"id": 7, "tier": "gold"}).handle
    engine.insert("Order", {"customer_id": 7, "amount": 5000})
    assert len(engine.activations()) == 1

    engine.retract(cust.id)
    assert engine.activations() == []
