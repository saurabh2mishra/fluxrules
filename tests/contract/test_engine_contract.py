from fluxrules.compat.contracts import EngineContract
from fluxrules.domain.models import Rule, RuleCondition, Ruleset
from fluxrules.engine.interpreter import InterpreterEngine


def test_interpreter_satisfies_engine_contract() -> None:
    engine: EngineContract = InterpreterEngine()
    ruleset = Ruleset(id="c", rules=(Rule(id="r", conditions=(RuleCondition("x", "eq", 1),)),))
    result = engine.evaluate(ruleset, {"x": 1})
    assert result.matched_rule_ids == ["r"]
