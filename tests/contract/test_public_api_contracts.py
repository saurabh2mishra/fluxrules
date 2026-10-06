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


def test_every_evaluation_path_shares_one_result_type() -> None:
    """One ``EvaluationResult``, reachable under both import paths.

    These were two classes whose ``matched_rule_ids`` meant opposite things
    ("fired" on the domain type, "considered" on the engine type). Collapsing
    them is the contract now, so this pins the identity rather than the split.
    """
    assert EvaluationResult is EngineEvaluationResult

    rule = Rule(
        name="amount-check",
        condition_dsl={"type": "condition", "field": "amount", "op": ">", "value": 100},
        action="review",
    )

    engine = PhreakEngine()
    engine.load_rules([rule])
    from_engine = engine.evaluate({"amount": 150})
    from_reference = ReferenceEvaluator().evaluate(
        Ruleset(group="contract", rules=(rule.to_engine_rule(),)),
        {"amount": 150},
    )
    from_public = evaluate(rule, {"amount": 150})

    for result in (from_engine, from_reference, from_public):
        assert type(result) is EvaluationResult
        assert result.fired_rules == [rule.id]
        assert result.actions == ["review"]
        assert not hasattr(result, "matched_rule_ids")


def test_public_evaluate_takes_rules_not_only_a_ruleset() -> None:
    """``evaluate`` must accept a bare rule; a Ruleset is no longer required."""
    assert signature(ReferenceEvaluator.evaluate).parameters.keys() >= {"ruleset", "facts"}
    assert signature(evaluate).parameters.keys() >= {"rules", "facts"}

    rule = Rule(
        name="amount-check",
        condition_dsl={"type": "condition", "field": "amount", "op": ">", "value": 100},
        action="review",
    )

    assert evaluate(rule, {"amount": 150}).fired_rules == [rule.id]
    assert evaluate([rule], {"amount": 150}).fired_rules == [rule.id]
    assert (
        evaluate(Ruleset(group="c", rules=(rule.to_engine_rule(),)), {"amount": 150}).fired_rules
        == [rule.id]
    )


def test_cross_fact_contract_is_dedicated_and_not_single_fact_registry() -> None:
    cross_fact = get_cross_fact_engine()

    assert hasattr(cross_fact, "insert")
    assert hasattr(cross_fact, "update")
    assert hasattr(cross_fact, "retract")
    assert not isinstance(cross_fact, BaseEngine)
    assert "CROSS_FACT" not in get_available_engines()
