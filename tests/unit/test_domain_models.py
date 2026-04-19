from fluxrules.domain.models import Rule, RuleCondition, Ruleset


def test_ruleset_holds_rules() -> None:
    rule = Rule(id="r1", conditions=(RuleCondition(fact="score", operator="gte", value=10),))
    ruleset = Ruleset(id="rs1", rules=(rule,))
    assert ruleset.rules[0].id == "r1"
