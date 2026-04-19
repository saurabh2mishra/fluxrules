import pytest

from fluxrules.domain.models import Rule, RuleCondition, Ruleset
from fluxrules.services.rule_service import RuleService


def test_rule_service_evaluates_saved_ruleset() -> None:
    service = RuleService.default()
    ruleset = Ruleset(
        id="approval",
        rules=(
            Rule(id="approved", conditions=(RuleCondition("risk", "lte", 3),), actions=("approve",)),
        ),
    )
    service.save_ruleset(ruleset)
    result = service.evaluate("approval", {"risk": 2})
    assert result.actions == ["approve"]


def test_rule_service_can_explain_execution() -> None:
    service = RuleService.default()
    ruleset = Ruleset(
        id="approval",
        rules=(Rule(id="approved", conditions=(RuleCondition("risk", "lte", 3),), actions=("approve",)),),
    )
    service.save_ruleset(ruleset)
    result = service.evaluate("approval", {"risk": 2})
    explanation = service.explain(result.execution_id)
    assert explanation.execution_id == result.execution_id


def test_rule_service_validation_rejects_unsupported_operator() -> None:
    service = RuleService.default()
    bad = Ruleset(
        id="bad",
        rules=(Rule(id="r1", conditions=(RuleCondition("risk", "between", [1, 3]),), actions=("x",)),),
    )
    with pytest.raises(ValueError):
        service.evaluate_inline(bad, {"risk": 2})
