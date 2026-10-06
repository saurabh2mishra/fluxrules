"""Public conformance helpers for third-party FluxRules engines.

The single entry point is :func:`assert_engine_contract`, which drives a
candidate :class:`~fluxrules.engine.base.BaseEngine` implementation against the
dependency-free :class:`~fluxrules.services.reference_evaluator.ReferenceEvaluator`
oracle across a battery of rule shapes. Two independent implementations agreeing
on every case is a far stronger correctness signal than a self-comparison.

Example::

    from fluxrules.testing import assert_engine_contract
    from my_pkg import MyEngine

    def test_my_engine_is_conformant():
        assert_engine_contract(MyEngine)

Pass an engine class, a zero-argument factory, or an instance (its class is used
to build a fresh engine per case, since ``load_rules`` mutates engine state).
"""

from __future__ import annotations

import warnings
from collections.abc import Callable
from dataclasses import dataclass, field

from fluxrules.domain.models import Ruleset
from fluxrules.domain.unified_rule import Rule
from fluxrules.engine.base import BaseEngine
from fluxrules.services.reference_evaluator import ReferenceEvaluator

__all__ = [
    "EngineContractCase",
    "assert_engine_contract",
    "default_contract_cases",
]

EngineFactory = type[BaseEngine] | Callable[[], BaseEngine] | BaseEngine


@dataclass(frozen=True)
class EngineContractCase:
    """A single conformance scenario: rules plus the fact to evaluate.

    Attributes:
        name: Human-readable label used in failure messages.
        rules: Canonical :class:`~fluxrules.Rule` objects to load.
        facts: A single flat fact map to evaluate against the rules.
    """

    name: str
    rules: tuple[Rule, ...]
    facts: dict[str, object] = field(default_factory=dict)


def _rule(rule_id: int, dsl: dict, *, priority: int = 0) -> Rule:
    return Rule(
        id=rule_id,
        name=f"rule_{rule_id}",
        condition_dsl=dsl,
        action="flag",
        priority=priority,
    )


def _cond(field_name: str, op: str, value: object) -> dict:
    return {"type": "condition", "field": field_name, "op": op, "value": value}


def default_contract_cases() -> list[EngineContractCase]:
    """The built-in conformance battery: one representative case per rule shape.

    Covers a bare leaf, AND / OR, nested boolean logic, numeric/string/bool
    operators, multi-rule fan-out, priority ordering, and a deliberate no-match.
    """
    and_dsl = {"type": "and", "children": [_cond("amount", ">", 100), _cond("country", "==", "US")]}
    or_dsl = {"type": "or", "children": [_cond("amount", ">", 100), _cond("country", "==", "US")]}
    nested_dsl = {
        "type": "and",
        "children": [
            _cond("amount", ">", 100),
            {"type": "or", "children": [_cond("country", "==", "US"), _cond("vip", "==", True)]},
        ],
    }
    return [
        EngineContractCase("leaf_match", (_rule(1, _cond("amount", ">", 100)),), {"amount": 500}),
        EngineContractCase("leaf_no_match", (_rule(1, _cond("amount", ">", 100)),), {"amount": 5}),
        EngineContractCase("and_match", (_rule(2, and_dsl),), {"amount": 500, "country": "US"}),
        EngineContractCase("and_partial", (_rule(2, and_dsl),), {"amount": 500, "country": "UK"}),
        EngineContractCase("or_left", (_rule(3, or_dsl),), {"amount": 500, "country": "UK"}),
        EngineContractCase("or_right", (_rule(3, or_dsl),), {"amount": 5, "country": "US"}),
        EngineContractCase("or_none", (_rule(3, or_dsl),), {"amount": 5, "country": "UK"}),
        EngineContractCase(
            "nested_true", (_rule(4, nested_dsl),), {"amount": 500, "country": "UK", "vip": True}
        ),
        EngineContractCase(
            "nested_false", (_rule(4, nested_dsl),), {"amount": 50, "country": "US", "vip": True}
        ),
        EngineContractCase(
            "multi_rule_fanout",
            (
                _rule(5, _cond("amount", ">", 100)),
                _rule(6, _cond("country", "==", "US")),
                _rule(7, _cond("vip", "==", True)),
            ),
            {"amount": 500, "country": "US", "vip": False},
        ),
        EngineContractCase(
            "priority_ordering",
            (
                _rule(8, _cond("amount", ">", 100), priority=1),
                _rule(9, _cond("amount", ">", 100), priority=5),
            ),
            {"amount": 500},
        ),
        EngineContractCase(
            "string_eq", (_rule(10, _cond("status", "==", "open")),), {"status": "open"}
        ),
        EngineContractCase("bool_eq", (_rule(11, _cond("vip", "==", True)),), {"vip": True}),
    ]


def _make_factory(engine: EngineFactory) -> Callable[[], BaseEngine]:
    if isinstance(engine, BaseEngine):
        engine_cls = type(engine)
        return engine_cls
    if isinstance(engine, type):
        if not issubclass(engine, BaseEngine):
            raise TypeError(f"Engine class must subclass BaseEngine, got {engine!r}.")
        return engine
    if callable(engine):
        return engine
    raise TypeError(
        "assert_engine_contract expects a BaseEngine subclass, a zero-argument "
        f"factory, or a BaseEngine instance; got {engine!r}."
    )


def _reference_fired(rules: tuple[Rule, ...], facts: dict[str, object]) -> set[int]:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        ruleset = Ruleset(group="contract", rules=tuple(r.to_engine_rule() for r in rules))
        result = ReferenceEvaluator().evaluate(ruleset, facts)
        return set(result.fired_rules)


def _candidate_fired(
    factory: Callable[[], BaseEngine], rules: tuple[Rule, ...], facts: dict[str, object]
) -> set[int]:
    engine = factory()
    if not isinstance(engine, BaseEngine):
        raise TypeError(f"Engine factory produced {engine!r}, which is not a BaseEngine.")
    engine.load_rules(list(rules))
    return set(engine.evaluate(facts).fired_rules)


def assert_engine_contract(
    engine: EngineFactory,
    *,
    cases: list[EngineContractCase] | None = None,
) -> None:
    """Assert a candidate engine agrees with the reference evaluator on every case.

    Args:
        engine: A :class:`~fluxrules.engine.base.BaseEngine` subclass, a
            zero-argument factory returning a fresh engine, or an instance
            (its class is reused to build a fresh engine per case).
        cases: Optional custom battery; defaults to :func:`default_contract_cases`.

    Raises:
        AssertionError: If the candidate's fired-rule set differs from the
            reference on any case. The message names the case and both sets.
        TypeError: If ``engine`` cannot be turned into a ``BaseEngine`` factory.
    """
    factory = _make_factory(engine)
    battery = cases if cases is not None else default_contract_cases()
    if not battery:
        raise ValueError("assert_engine_contract needs at least one case.")

    mismatches: list[str] = []
    for case in battery:
        expected = _reference_fired(case.rules, case.facts)
        actual = _candidate_fired(factory, case.rules, case.facts)
        if actual != expected:
            mismatches.append(
                f"  - {case.name}: expected fired={sorted(expected)}, "
                f"got fired={sorted(actual)} for facts={case.facts}"
            )

    if mismatches:
        raise AssertionError(
            "Engine does not conform to the FluxRules reference contract:\n" + "\n".join(mismatches)
        )
