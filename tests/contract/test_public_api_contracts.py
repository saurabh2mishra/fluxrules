"""Public API contract-family and stability-boundary checks."""

from __future__ import annotations

from inspect import signature

from fluxrules import EvaluationResult, Rule, Ruleset, evaluate
from fluxrules.engine import BaseEngine, get_available_engines, get_cross_fact_engine, get_engine
from fluxrules.engine.infrastructure import EvaluationResult as EngineEvaluationResult
from fluxrules.engine.phreak import PhreakEngine
from fluxrules.services.reference_evaluator import ReferenceEvaluator


def test_stable_single_fact_contract_is_explicit() -> None:
    assert issubclass(PhreakEngine, BaseEngine)
    assert "PHREAK" in get_available_engines()
    assert isinstance(get_engine("PHREAK"), PhreakEngine)

    rule = Rule(
        name="amount-check",
        condition_dsl={"type": "condition", "field": "amount", "op": ">", "value": 100},
        action="review",
        persist=False,
    )
    engine = PhreakEngine()
    engine.load_rules([rule])
    result = engine.evaluate({"amount": 150})

    assert result.fired_rules == [rule.id]
    assert result.actions == ["review"]


def test_reference_contract_has_a_distinct_domain_result_shape() -> None:
    assert signature(ReferenceEvaluator.evaluate).parameters.keys() >= {"ruleset", "facts"}
    assert signature(evaluate).parameters.keys() >= {"ruleset", "facts"}
    assert EvaluationResult is not EngineEvaluationResult

    rule = Rule(
        name="amount-check",
        condition_dsl={"type": "condition", "field": "amount", "op": ">", "value": 100},
        action="review",
        persist=False,
    )
    result = ReferenceEvaluator().evaluate(
        Ruleset(group="contract", rules=(rule.to_engine_rule(),)),
        {"amount": 150},
    )

    assert result.matched_rule_ids == [rule.id]
    assert result.actions == ["review"]


def test_cross_fact_contract_is_dedicated_and_not_single_fact_registry() -> None:
    cross_fact = get_cross_fact_engine()

    assert hasattr(cross_fact, "insert")
    assert hasattr(cross_fact, "update")
    assert hasattr(cross_fact, "retract")
    assert not isinstance(cross_fact, BaseEngine)
    assert "CROSS_FACT" not in get_available_engines()
