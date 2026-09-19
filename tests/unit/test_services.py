import pytest

from fluxrules.domain.models import EngineRule, RuleCondition, Ruleset
from fluxrules.services.rule_service import RuleService


def test_rule_service_evaluates_saved_ruleset() -> None:
    service = RuleService.create()
    ruleset = Ruleset(
        group="approval",
        rules=(
            EngineRule(
                id=1,
                name="approved",
                conditions=(RuleCondition("risk", "lte", 3),),
                actions=("approve",),
            ),
        ),
    )
    service.persist(ruleset)
    result = service.evaluate_ruleset("approval", {"risk": 2})
    assert result.actions == ["approve"]


def test_rule_service_can_explain_execution() -> None:
    service = RuleService.create()
    ruleset = Ruleset(
        group="approval",
        rules=(
            EngineRule(
                id=1,
                name="approved",
                conditions=(RuleCondition("risk", "lte", 3),),
                actions=("approve",),
            ),
        ),
    )
    service.persist(ruleset)
    result = service.evaluate_ruleset("approval", {"risk": 2})
    explanation = service.explain(result.execution_id)
    assert explanation.execution_id == result.execution_id


def test_rule_service_validation_rejects_unsupported_operator() -> None:
    with pytest.raises(ValueError):
        RuleCondition("risk", "between", [1, 3])


def test_rule_service_persist() -> None:
    """Verify that ``persist()`` stores the ruleset and it can be evaluated."""
    service = RuleService.create()
    ruleset = Ruleset(
        group="persist_test",
        rules=(
            EngineRule(
                id=99,
                name="r99",
                conditions=(RuleCondition("x", "gt", 0),),
                actions=("ok",),
            ),
        ),
    )
    service.persist(ruleset)
    result = service.evaluate_ruleset("persist_test", {"x": 1})
    assert result.actions == ["ok"]
