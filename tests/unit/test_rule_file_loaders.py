"""Direct contract tests for the YAML rule loader and canonical Rule validation."""

from __future__ import annotations

from fluxrules import Rule
from fluxrules.adapters.loaders.yaml_loader import load_rules_from_yaml
from fluxrules.engine.phreak import PhreakEngine


def _evaluate(rule_data: dict, facts: dict) -> list[int]:
    rule = Rule.model_validate_yaml({**rule_data, "persist": False})
    engine = PhreakEngine()
    engine.load_rules([rule])
    return engine.evaluate(facts).fired_rules


def test_yaml_loader_returns_canonical_rule_data_and_phreak_evaluates(tmp_path) -> None:
    path = tmp_path / "rules.yaml"
    path.write_text(
        """- id: 7
  name: high_value
  action: review
  condition_dsl:
    type: condition
    field: amount
    op: ">"
    value: 100
"""
    )

    rows = load_rules_from_yaml(str(path))

    assert rows[0]["condition_dsl"]["field"] == "amount"
    assert _evaluate(rows[0], {"amount": 150}) == [7]
    assert _evaluate(rows[0], {"amount": 50}) == []


def test_yaml_loader_accepts_single_mapping(tmp_path) -> None:
    path = tmp_path / "rule.yaml"
    path.write_text(
        """id: 8
name: country_check
action: review
condition_dsl:
  type: condition
  field: country
  op: ==
  value: US
"""
    )

    rows = load_rules_from_yaml(str(path))

    assert len(rows) == 1
    assert rows[0]["id"] == 8









