"""Parity + unit tests for the segment-level condition compiler.

Condition compilation must be an *invisible* optimization: for any fact, the set
of fired rules with ``compile_conditions=True`` must equal the set with it OFF.
It may only make per-rule evaluation faster by inlining the boolean structure;
leaves still delegate to ``evaluate_operator`` and dynamic nodes (``accumulate``)
fall back to the interpreter, so results never change.

Two layers of coverage:

1. Engine-level A/B parity: compiled ON vs OFF over randomized rules/facts.
2. Compiler unit tests: the closure produced by ``compile_condition`` agrees
   with a reference interpreter for every node type, including degenerate
   (empty AND/OR/NOT) cases and the per-node ``fallback_factory`` path.
"""

from __future__ import annotations

import random

import pytest

from fluxrules import Rule
from fluxrules.engine.configuration import EngineConfig
from fluxrules.engine.operators import evaluate_operator
from fluxrules.engine.phreak._engine import PhreakEngine
from fluxrules.engine.phreak.condition_compiler import compile_condition

# Helpers


def _rule(rid: int, dsl: dict) -> Rule:
    return Rule(id=rid, name=f"r{rid}", condition_dsl=dsl, priority=rid % 5, persist=False)


def _leaf(field: str, op: str, value) -> dict:
    return {"type": "condition", "field": field, "op": op, "value": value}


_FIELDS = [f"f{i}" for i in range(6)]
_OPS = [">", ">=", "<", "<=", "==", "!="]


def _rand_dsl(rng: random.Random, depth: int = 0) -> dict:
    """Build a randomized (possibly nested) condition tree."""
    if depth >= 2 or rng.random() < 0.45:
        return _leaf(rng.choice(_FIELDS), rng.choice(_OPS), rng.randint(0, 50))

    kind = rng.choice(["and", "or", "not"])
    if kind == "not":
        return {"type": "not", "condition": _rand_dsl(rng, depth + 1)}
    n = rng.randint(2, 3)
    return {
        "type": kind,
        "conditions": [_rand_dsl(rng, depth + 1) for _ in range(n)],
    }


def _rand_fact(rng: random.Random) -> dict:
    return {f: rng.randint(0, 50) for f in _FIELDS if rng.random() < 0.8}


def _reference(condition, facts: dict, flags) -> bool:
    """Independent interpreter used as the oracle for unit tests."""
    if not isinstance(condition, dict):
        return False
    ctype = condition.get("type")
    if ctype == "condition":
        field = condition.get("field", "")
        return evaluate_operator(
            condition.get("op", "=="),
            facts.get(field),
            rule_value=condition.get("value"),
            field_present=field in facts,
            strict_null_handling=flags.strict_null_handling,
            strict_type_comparison=flags.strict_type_comparison,
            boolean_string_coercion=flags.boolean_string_coercion,
        )
    if ctype in ("composite", "group", "and", "or"):
        if ctype == "and":
            logic = "AND"
        elif ctype == "or":
            logic = "OR"
        else:
            logic = (condition.get("logic") or condition.get("op", "AND")).upper()
        children = condition.get("conditions") or condition.get("children") or []
        results = [_reference(c, facts, flags) for c in children]
        return all(results) if logic == "AND" else any(results)
    if ctype == "not":
        inner = condition.get("condition")
        if inner is not None:
            return not _reference(inner, facts, flags)
        inner_list = condition.get("conditions") or []
        return not any(_reference(c, facts, flags) for c in inner_list)
    if ctype == "exists":
        field = condition.get("field")
        if field:
            return field in facts and facts[field] is not None
        inner = condition.get("condition")
        return _reference(inner, facts, flags) if inner else False
    return False


# 1. Engine-level A/B parity


@pytest.mark.parametrize("seed", [1, 13, 99, 2024, 7777])
def test_compiled_vs_interpreter_fired_rules_parity(seed: int) -> None:
    rng = random.Random(seed)
    rules = [_rule(i, _rand_dsl(rng)) for i in range(40)]
    facts = [_rand_fact(rng) for _ in range(600)]

    on = PhreakEngine(compile_conditions=True)
    on.load_rules(rules)
    off = PhreakEngine(compile_conditions=False)
    off.load_rules(rules)

    for fact in facts:
        got = set(on.evaluate(fact).fired_rules)
        expected = set(off.evaluate(fact).fired_rules)
        assert got == expected, f"divergence on {fact}: {got} != {expected}"


def test_compiled_combined_with_alpha_prefilter_parity() -> None:
    """Both optimizations together must still equal the plain interpreter."""
    rng = random.Random(31337)
    rules = [_rule(i, _rand_dsl(rng)) for i in range(50)]
    facts = [_rand_fact(rng) for _ in range(500)]

    both = PhreakEngine(compile_conditions=True, alpha_prefilter=True)
    both.load_rules(rules)
    plain = PhreakEngine(compile_conditions=False, alpha_prefilter=False)
    plain.load_rules(rules)

    for fact in facts:
        assert set(both.evaluate(fact).fired_rules) == set(plain.evaluate(fact).fired_rules)


# 2. Compiler unit tests


@pytest.mark.parametrize("seed", range(20))
def test_compile_condition_matches_reference(seed: int) -> None:
    rng = random.Random(seed)
    flags = EngineConfig()
    for _ in range(25):
        dsl = _rand_dsl(rng)
        compiled = compile_condition(dsl, flags)
        for _ in range(20):
            fact = _rand_fact(rng)
            assert compiled(fact) == _reference(dsl, fact, flags)


def test_compile_degenerate_nodes() -> None:
    flags = EngineConfig()
    # Empty AND -> True; empty OR -> False; empty NOT-list -> True.
    assert compile_condition({"type": "and", "conditions": []}, flags)({}) is True
    assert compile_condition({"type": "or", "conditions": []}, flags)({}) is False
    assert compile_condition({"type": "not", "conditions": []}, flags)({}) is True
    # Unknown node compiles to constant False (matches interpreter).
    assert compile_condition({"type": "mystery"}, flags)({}) is False
    # Non-dict input -> False.
    assert compile_condition("nonsense", flags)({}) is False  # type: ignore[arg-type]


def test_compile_or_logic_via_logic_key() -> None:
    flags = EngineConfig()
    dsl = {
        "type": "composite",
        "logic": "OR",
        "conditions": [_leaf("a", "==", 1), _leaf("b", "==", 2)],
    }
    fn = compile_condition(dsl, flags)
    assert fn({"a": 1}) is True
    assert fn({"b": 2}) is True
    assert fn({"a": 0, "b": 0}) is False


def test_compile_accumulate_uses_per_node_fallback() -> None:
    """A dynamic node nested in an AND must use the *per-node* fallback.

    If the fallback were bound to the root instead of the node, an AND child
    that is an ``accumulate`` would re-evaluate the whole tree and diverge.
    """
    flags = EngineConfig()
    seen_nodes = []

    def factory(node):
        seen_nodes.append(node)
        # Pretend this dynamic node is True only when 'agg' >= 10.
        return lambda facts: facts.get("agg", 0) >= 10

    dsl = {
        "type": "and",
        "conditions": [
            _leaf("a", "==", 1),
            {"type": "accumulate", "marker": "dynamic"},
        ],
    }
    fn = compile_condition(dsl, flags, fallback_factory=factory)

    # The factory must have been called with the accumulate node itself.
    assert len(seen_nodes) == 1
    assert seen_nodes[0]["marker"] == "dynamic"

    assert fn({"a": 1, "agg": 10}) is True
    assert fn({"a": 1, "agg": 9}) is False  # dynamic child False
    assert fn({"a": 0, "agg": 99}) is False  # leaf False, short-circuits


def test_compile_accumulate_without_fallback_is_false() -> None:
    flags = EngineConfig()
    fn = compile_condition({"type": "accumulate"}, flags)
    assert fn({"anything": 1}) is False
