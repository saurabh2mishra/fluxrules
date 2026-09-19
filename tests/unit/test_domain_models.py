from fluxrules.domain.models import EngineRule, RuleCondition, Ruleset


def test_ruleset_holds_rules() -> None:
    rule = EngineRule(
        id=1,
        name="r1",
        conditions=(RuleCondition(fact="score", operator="gte", value=10),),
    )
    ruleset = Ruleset(group="rs1", rules=(rule,))
    assert ruleset.rules[0].id == 1
