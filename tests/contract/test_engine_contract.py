from fluxrules.compat.contracts import EngineContract
from fluxrules.domain.models import EngineRule, RuleCondition, Ruleset
from fluxrules.services.reference_evaluator import ReferenceEvaluator


def test_reference_evaluator_satisfies_engine_contract() -> None:
    engine: EngineContract = ReferenceEvaluator()
    ruleset = Ruleset(
        group="contract",
        rules=(EngineRule(id=1, name="r", conditions=(RuleCondition("x", "eq", 1),)),),
    )
    result = engine.evaluate(ruleset, {"x": 1})
    assert result.matched_rule_ids == [1]
