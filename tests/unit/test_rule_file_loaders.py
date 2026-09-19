"""Direct contract tests for YAML/CSV rule loaders and canonical Rule validation."""

from __future__ import annotations

import csv
import json

import pytest

from fluxrules import Rule
from fluxrules.adapters.loaders.csv_loader import load_rules_from_csv
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


def test_csv_simple_style_groups_same_id_into_and(tmp_path) -> None:
    path = tmp_path / "rules.csv"
    with path.open("w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["id", "name", "priority", "fact", "operator", "value", "action"])
        writer.writerow([7, "high_us", 10, "amount", ">", 100, "review"])
        writer.writerow([7, "high_us", 10, "country", "==", "US", "review"])

    rows = load_rules_from_csv(str(path))

    assert rows[0]["condition_dsl"]["op"] == "AND"
    assert _evaluate(rows[0], {"amount": 150, "country": "US"}) == [7]
    assert _evaluate(rows[0], {"amount": 150, "country": "GB"}) == []


def test_csv_dsl_style_preserves_or_tree_and_canonical_validation(tmp_path) -> None:
    path = tmp_path / "rules.csv"
    dsl = {
        "type": "or",
        "conditions": [
            {"type": "condition", "field": "amount", "op": ">", "value": 100},
            {"type": "condition", "field": "country", "op": "==", "value": "US"},
        ],
    }
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["id", "name", "priority", "condition_dsl", "action", "enabled"],
        )
        writer.writeheader()
        writer.writerow(
            {
                "id": 9,
                "name": "or_rule",
                "priority": 1,
                "condition_dsl": json.dumps(dsl),
                "action": "review",
                "enabled": "true",
            }
        )

    rows = load_rules_from_csv(str(path))

    assert rows[0]["condition_dsl"] == dsl
    assert _evaluate(rows[0], {"amount": 150, "country": "GB"}) == [9]
    assert _evaluate(rows[0], {"amount": 50, "country": "GB"}) == []


def test_csv_dsl_style_rejects_invalid_json(tmp_path) -> None:
    path = tmp_path / "bad.csv"
    path.write_text("id,name,priority,condition_dsl,action\n1,bad,1,{not-json},review\n")

    with pytest.raises(ValueError, match="condition_dsl is not valid JSON"):
        load_rules_from_csv(str(path))
