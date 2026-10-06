from fluxrules import Rule, RuleBuilder, evaluate, explain, validate
from fluxrules.domain.models import EngineRule, RuleCondition, Ruleset

_ADULT_DSL = {"type": "condition", "field": "age", "op": ">=", "value": 18}


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
    assert payload["fired_rules"] == [1]


def test_evaluate_accepts_a_single_rule() -> None:
    """The documented one-liner: no Ruleset, no to_engine_rule() hop."""
    rule = Rule(id=1, name="adult", condition_dsl=_ADULT_DSL, action="allow")

    result = evaluate(rule, {"age": 30})

    assert result.fired_rules == [1]
    assert result.actions == ["allow"]


def test_evaluate_accepts_a_list_of_rules() -> None:
    rules = [
        Rule(id=1, name="adult", condition_dsl=_ADULT_DSL, action="allow"),
        Rule(
            id=2,
            name="vip",
            condition_dsl={"type": "condition", "field": "vip", "op": "==", "value": True},
            action="fast_track",
        ),
    ]

    result = evaluate(rules, {"age": 30, "vip": True})

    assert sorted(result.fired_rules) == [1, 2]
    assert sorted(result.actions) == ["allow", "fast_track"]


def test_evaluate_accepts_a_built_rule() -> None:
    rule = (
        RuleBuilder(7)
        .name("adult")
        .condition(_ADULT_DSL)
        .action("allow")
        .build()
    )

    assert evaluate(rule, {"age": 30}).fired_rules == [7]


def test_evaluate_accepts_a_generator_of_rules() -> None:
    rules = (Rule(id=i, name=f"r{i}", condition_dsl=_ADULT_DSL, action="allow") for i in (1, 2))

    assert sorted(evaluate(rules, {"age": 30}).fired_rules) == [1, 2]


def test_validate_accepts_the_same_shapes() -> None:
    rule = Rule(id=1, name="adult", condition_dsl=_ADULT_DSL, action="allow")

    assert validate(rule) == []
    assert validate([rule]) == []


def test_evaluate_rejects_a_non_rule_with_an_actionable_message() -> None:
    import pytest

    with pytest.raises(TypeError, match="fluxrules.Rule"):
        evaluate(["not a rule"], {"age": 30})
