from fluxrules.domain.models import Rule, RuleCondition, Ruleset
from fluxrules.engine.interpreter import InterpreterEngine


def test_interpreter_matches_rule_and_actions() -> None:
    ruleset = Ruleset(
        id="eligibility",
        rules=(
            Rule(
                id="adult",
                conditions=(RuleCondition(fact="age", operator="gte", value=18),),
                actions=("allow",),
                priority=10,
            ),
        ),
    )
    result = InterpreterEngine().evaluate(ruleset, {"age": 30})
    assert result.matched_rule_ids == ["adult"]
    assert result.actions == ["allow"]
