# YAML & CSV Rules

**Prerequisites:** [Conditions](conditions.md) and [Rule Types](rule-types.md).

FluxRules provides raw YAML and CSV file loaders. The loaders return rule
mappings; the canonical `Rule` model remains the validation boundary before
rules are passed to `PhreakEngine`.

## YAML

YAML files contain either one mapping or a list of mappings using the canonical
`Rule` fields. `condition_dsl` is the full condition tree.

```yaml
- id: 7
  name: high_value
  action: review
  condition_dsl:
    type: condition
    field: amount
    op: ">"
    value: 100
```

Load and validate the mappings explicitly:

```python skip
from fluxrules import Rule
from fluxrules.adapters.loaders.yaml_loader import load_rules_from_yaml
from fluxrules.engine.phreak import PhreakEngine

rows = load_rules_from_yaml("rules.yaml")
rules = [Rule.model_validate_yaml({**row, "persist": False}) for row in rows]

engine = PhreakEngine()
engine.load_rules(rules)
result = engine.evaluate({"amount": 150})
assert result.fired_rules == [7]
```

The loader requires the `yaml` extra:

```bash
pip install 'fluxrules[yaml]'
```

## CSV decision tables

CSV supports two rule styles.

### Simple style

One condition per row. Rows with the same `id` are grouped into an `AND` tree:

```csv
id,name,priority,fact,operator,value,action,enabled
7,high_us,10,amount,>,100,review,true
7,high_us,10,country,==,US,review,true
```

### DSL style

Use a JSON object in `condition_dsl` for `OR`, nested groups, and other DSL
shapes:

```csv
id,name,priority,condition_dsl,action,enabled
9,or_rule,1,"{""type"":""or"",""conditions"":[{""type"":""condition"",""field"":""amount"",""op"":"">"",""value"":100},{""type"":""condition"",""field"":""country"",""op"":""=="",""value"":""US""}]}",review,true
```

Load and validate CSV rules:

```python skip
from fluxrules import Rule
from fluxrules.adapters.loaders.csv_loader import load_rules_from_csv
from fluxrules.engine.phreak import PhreakEngine

rows = load_rules_from_csv("rules.csv")
rules = [Rule.model_validate_csv_row({**row, "persist": False}) for row in rows]

engine = PhreakEngine()
engine.load_rules(rules)
result = engine.evaluate({"amount": 150, "country": "GB"})
assert result.fired_rules == [7]
```

The CSV loader is part of the core adapter module and accepts numeric values,
boolean `enabled`, simple grouped rows, and JSON DSL values. Invalid JSON or
missing required columns raises `ValueError` before a rule reaches the engine.

## Canonical validation boundary

The raw loaders intentionally return dictionaries so applications can inspect,
merge, or annotate imported rules. Always pass each mapping through the
canonical validator before loading it:

```python
from fluxrules import Rule

rule = Rule.model_validate_yaml(
    {
        "name": "country_check",
        "condition_dsl": {
            "type": "condition",
            "field": "country",
            "op": "==",
            "value": "US",
        },
        "action": "review",
        "persist": False,
    }
)
```

This rejects empty logic, unknown operators, malformed DSL structure, and
conflicting action fields at the authoring boundary.

## Operational guidance

Store YAML and CSV rule files in version control, validate them in CI, and
record the generated rule-set version used by a deployment. The loader does
not execute action handlers; evaluation returns action names and the application
or action dispatcher owns side effects.

For persistence-backed rule management, use `RuleService` and `Ruleset` rather
than treating a file loader as a database repository.

## Next Steps

- [Conditions](conditions.md)
- [Rule Types](rule-types.md)
- [Custom Actions](custom-actions.md)
- [Persistence](persistence.md)
