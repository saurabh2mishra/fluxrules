import logging

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
                condition_nodes=(RuleCondition(fact="age", operator="gte", value=18),),
                actions=("allow",),
                priority=10,
            ),
        ),
    )
    result = ReferenceEvaluator().evaluate(ruleset, {"age": 30})
    assert result.fired_rules == [1]
    assert result.actions == ["allow"]


def test_reference_evaluator_accepts_canonical_rule() -> None:
    ruleset = Ruleset(
        group="eligibility",
        rules=(
            CanonicalRule(
                id=7,
                name="adult",
                conditions={
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
    assert result.fired_rules == [7]
    assert result.actions == ["allow"]


def test_reference_evaluator_declines_stateful_node(caplog) -> None:
    """A rule whose conditions DSL contains a stateful node must not crash the evaluator.

    The reference evaluator catches UnsupportedConditionTreeNodeError, logs a
    warning, and returns False (no match) rather than raising or silently
    returning True.
    """
    ruleset = Ruleset(
        group="g",
        rules=(
            EngineRule(
                id=5,
                name="stateful",
                actions=("alert",),
                priority=1,
                group="g",
                conditions={"type": "sequence", "steps": [
                    {"type": "condition", "field": "x", "op": ">", "value": 0},
                    {"type": "condition", "field": "y", "op": ">", "value": 0},
                ]},
            ),
        ),
    )
    with caplog.at_level(logging.WARNING):
        result = ReferenceEvaluator().evaluate(ruleset, {"x": 1, "y": 1})

    assert result.fired_rules == []
    assert any("reference evaluator" in r.message.lower() for r in caplog.records)


def test_reference_evaluator_or_rule_via_conditions_tree() -> None:
    """An OR rule evaluated via the conditions DSL must fire on either branch."""
    ruleset = Ruleset(
        group="g",
        rules=(
            EngineRule(
                id=3,
                name="or_rule",
                actions=("flag",),
                priority=1,
                group="g",
                conditions={
                    "type": "or",
                    "conditions": [
                        {"type": "condition", "field": "status", "op": "==", "value": "vip"},
                        {"type": "condition", "field": "amount", "op": ">", "value": 1000},
                    ],
                },
            ),
        ),
    )
    evaluator = ReferenceEvaluator()
    assert evaluator.evaluate(ruleset, {"status": "vip", "amount": 0}).fired_rules == [3]
    assert evaluator.evaluate(ruleset, {"status": "regular", "amount": 2000}).fired_rules == [3]
    assert evaluator.evaluate(ruleset, {"status": "regular", "amount": 50}).fired_rules == []
