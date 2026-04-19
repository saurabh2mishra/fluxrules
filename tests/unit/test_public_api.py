from fluxrules import evaluate, explain
from fluxrules.domain.models import Rule, RuleCondition, Ruleset


def test_public_evaluate_and_explain() -> None:
    ruleset = Ruleset(
        id="eligibility",
        rules=(Rule(id="adult", conditions=(RuleCondition("age", "gte", 18),), actions=("allow",)),),
    )
    result = evaluate(ruleset, {"age": 30})
    payload = explain(result.execution_id)
    assert payload["matched_rules"] == ["adult"]
