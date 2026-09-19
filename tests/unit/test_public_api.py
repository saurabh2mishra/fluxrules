from fluxrules import evaluate, explain
from fluxrules.domain.models import EngineRule, RuleCondition, Ruleset


def test_public_evaluate_and_explain() -> None:
    ruleset = Ruleset(
        group="eligibility",
        rules=(
            EngineRule(
                id=1,
                name="adult",
                conditions=(RuleCondition("age", "gte", 18),),
                actions=("allow",),
            ),
        ),
    )
    result = evaluate(ruleset, {"age": 30})
    payload = explain(result.execution_id)
    assert payload["matched_rules"] == [1]
