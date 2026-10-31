# YAML Rules

**Prerequisites:** [Authoring Rules](authoring-rules.md), [Conditions](conditions.md) and [Rule Types](rule-types.md).

FluxRules provides a YAML file loader. It returns rule mappings; the canonical
`Rule` model remains the validation boundary before rules are passed to
`PhreakEngine`.

## YAML

A YAML rule file holds one of three shapes, using the canonical `Rule` fields.
`conditions` is the full condition tree.

A list of rules:

```yaml
- id: 7
  name: high_value
  action: review
  conditions:
    type: condition
    field: amount
    op: ">"
    value: 100
```

A single rule mapping (the same fields, without the leading `-`).

Or a mapping with a `rules` list and an optional `fact_schema`, naming the
model the rules are written against (see
[Check rules against a fact schema](#check-rules-against-a-fact-schema)):

```yaml
fact_schema: myapp.models:Payment
rules:
  - id: 7
    name: high_value
    action: review
    conditions: {type: condition, field: amount, op: ">", value: 100}
```

Load and validate the mappings explicitly:

```python
# python skip
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

`load_rules_from_yaml` returns the rule mappings in every case. To read a file
as JSON or YAML by its extension and also get its `fact_schema`, use
`read_rule_file`:

```python
# python skip
from fluxrules.adapters.loaders import read_rule_file

document = read_rule_file("rules.yaml")
document.rules  # list of rule mappings
document.fact_schema  # "myapp.models:Payment", or None
```

## Canonical validation boundary

The raw loader intentionally returns dictionaries so applications can inspect,
merge, or annotate imported rules. Always pass each mapping through the
canonical validator before loading it:

```python
from fluxrules import Rule

rule = Rule.model_validate_yaml(
    {
        "name": "country_check",
        "conditions": {
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

This rejects empty logic, unknown operators, malformed condition tree structure, and
conflicting action fields at the authoring boundary.

## Check rules against a fact schema

A rule that names a field the facts never carry (`account.ageDays` instead of
`account.age_days`) loads fine and then never matches. Naming the fact model
catches it when the file is loaded.

### In the file

Put `fact_schema` next to `rules`, as above. `load_rules_from_yaml` then checks
every field each rule references, including `exists` fields, and raises
`UnknownFieldError` with a suggestion before returning anything:

```text
UnknownFieldError: Rule 'high_value' references unknown field 'amout' (not in
fact schema Payment). Did you mean 'amount'? Known fields: [...]
```

`fact_schema` is an import string in one of two forms:

| Form | Example | Loads |
|---|---|---|
| Module | `myapp.models:Payment` | `Payment` from the module `myapp.models`; the current directory is searched |
| File | `models.py:Payment` | `Payment` from that file, resolved against the YAML file's directory |

Loading the schema imports its module, which runs that module's code. So
`load_rules_from_yaml` loads a schema the file names only when you say you
trust the file:

```python
# python skip
rows = load_rules_from_yaml("rules.yaml", trust_schema=True)
```

Without `trust_schema=True` it raises `ValueError` naming the file and the
schema. Passing `fact_schema=` yourself needs no flag, because then you chose
the model. A file that names a schema is tied to that import path: moving or
renaming the model class means updating the file.

### From Python

Pass `fact_schema=` to check against a model the file does not name, or to
override the one it names. It takes a class or an import string:

```python
# python skip
from myapp.models import Payment

from fluxrules.adapters.loaders.yaml_loader import load_rules_from_yaml

rows = load_rules_from_yaml("rules.yaml", fact_schema=Payment)
```

`load_rules_from_yaml` stops at the first unknown field. To list them all, use
`FactSchemaInfo.unknown_fields`:

```python
# python skip
from fluxrules.adapters.loaders import read_rule_file
from fluxrules.facts import load_schema, schema_info

document = read_rule_file("rules.yaml")
info = schema_info(load_schema(document.fact_schema, base_dir=document.path.parent))
for error in info.unknown_fields(document.rules):
    print(error.rule, error.field, error.suggestion)
```

An engine built with the same model checks again at `load_rules`:
`PhreakEngine(fact_schema=Payment)`. See [Typed Facts](typed-facts.md).

### From the command line

```bash
fluxrules validate rules/*.yaml
fluxrules validate rules/*.yaml --schema myapp.models:Payment
```

`fluxrules validate` reads YAML and JSON rule files, reports every unknown
field with a hint, and exits `1` when it finds one, so it can gate CI. The
schema comes from `--schema`, else the file's `fact_schema`, else `fact_schema`
in `fluxrules.yaml`. A schema named inside a file is loaded only with
`--trust-schema`. See [CLI](cli.md#trusting-a-schema-named-in-a-file).

## Operational guidance

Store YAML rule files in version control, validate them in CI
(`fluxrules validate rules/*.yaml`), and record the
generated rule-set version used by a deployment. The loader does not execute
action handlers; evaluation returns action names and the application or action
dispatcher owns side effects.

For persistence-backed rule management, use `RuleService` and `Ruleset` rather
than treating a file loader as a database repository.

## Next Steps

- [CLI](cli.md)
- [Typed Facts](typed-facts.md)
- [Conditions](conditions.md)
- [Rule Types](rule-types.md)
- [Custom Actions](custom-actions.md)
- [Persistence](persistence.md)