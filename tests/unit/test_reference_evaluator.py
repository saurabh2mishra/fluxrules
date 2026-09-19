from fluxrules.domain.models import EngineRule, RuleCondition, Ruleset
from fluxrules.domain.unified_rule import Rule as CanonicalRule
from fluxrules.services.reference_evaluator import ReferenceEvaluator


def test_reference_evaluator_matches_rule_and_actions() -> None:
    ruleset = Ruleset(
        group="eligibility",
        rules=(
            EngineRule(
                id=1,
                name="adult",
                conditions=(RuleCondition(fact="age", operator="gte", value=18),),
                actions=("allow",),
                priority=10,
            ),
        ),
    )
    result = ReferenceEvaluator().evaluate(ruleset, {"age": 30})
    assert result.matched_rule_ids == [1]
    assert result.actions == ["allow"]


def test_reference_evaluator_accepts_canonical_rule() -> None:
    ruleset = Ruleset(
        group="eligibility",
        rules=(
            CanonicalRule(
                id=7,
                name="adult",
                condition_dsl={
                    "type": "condition",
                    "field": "age",
                    "op": ">=",
                    "value": 18,
                },
                action="allow",
                priority=10,
                persist=False,
            ),
        ),
    )
    result = ReferenceEvaluator().evaluate(ruleset, {"age": 30})
    assert result.matched_rule_ids == [7]
    assert result.actions == ["allow"]
