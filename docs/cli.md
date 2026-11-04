# CLI

**Prerequisites:** [Installation](installation.md) and [YAML Rules](yaml-rules.md).

---

The `fluxrules` command validates rule files, evaluates an event against them,
scaffolds a project and starts the HTTP API. Install it with the `cli` extra:

```bash
pip install 'fluxrules[cli]'
fluxrules --help
```

| Command | Does |
|---|---|
| `fluxrules validate RULES...` | Checks rule files for structural issues and, with a fact schema, unknown fields |
| `fluxrules evaluate RULES INPUT` | Evaluates one JSON event against a rule file |
| `fluxrules init` | Scaffolds `rules.json`, `input.json` and `fluxrules.yaml` |
| `fluxrules serve` | Starts the HTTP API (needs the `api` extra) |
| `fluxrules version` | Prints the installed version |

## Rule files

`validate` and `evaluate` read `.json` files as JSON and `.yaml` / `.yml`
files as YAML (YAML needs the `yaml` extra). YAML values are read as written,
so `NO` is the text `"NO"`; see [How values are read](yaml-rules.md#how-values-are-read).
A rule file holds one of:

- a list of rule mappings,
- a single rule mapping,
- a mapping with a `rules` list and an optional `fact_schema`, naming the model
  the rules are written against:

```yaml
fact_schema: myapp.models:Payment
rules:
  - id: 1
    name: large_payment_new_account
    priority: 50
    action: manual_review
    conditions:
      type: and
      children:
        - {type: condition, field: amount, op: ">", value: 2000}
        - {type: condition, field: account.age_days, op: "<", value: 14}
```

The same shape works in JSON (`{"fact_schema": "...", "rules": [...]}`). Rule
mappings use the canonical `Rule` fields; see [YAML Rules](yaml-rules.md).

## validate

```bash
fluxrules validate rules/payments.yaml
fluxrules validate rules/*.yaml --schema myapp.models:Payment
```

Reports every problem it finds, not only the first:

- empty conditions, duplicate ids and unsupported operators;
- values that do not suit their operator, such as `amount > null` or a
  `regex` that does not compile (see
  [Values that suit the operator](conditions.md#values-that-suit-the-operator));
- YAML values that FluxRules 1.1 read differently, such as `NO` (see
  [How values are read](yaml-rules.md#how-values-are-read)).

With a fact schema it also reports every field a rule names that the model
lacks, each with a "did you mean" hint, and every value of the wrong type for
its field (see
[Rule values are checked too](typed-facts.md#rule-values-are-checked-too)).
Output is JSON:

```json
{
  "valid": false,
  "issues": [
    "Rule 'large_payment_new_account' references unknown field 'account.ageDays' (not in fact schema Payment). Did you mean 'account.age_days'?",
    "Rule 'high_risk_country' references unknown field 'account.contry' (not in fact schema Payment). Did you mean 'account.country'?"
  ],
  "schemas": [
    {
      "file": "rules/payments.yaml",
      "fact_schema": "myapp.models:Payment",
      "source": "rule file rules/payments.yaml"
    }
  ]
}
```

`schemas` says, per file, which schema was used and where it came from. With
several files, each issue starts with its file name.

| Option | Meaning |
|---|---|
| `--schema SPEC` | Fact schema to check against. Overrides the rule file and the config. |
| `--config PATH` | Config file to read `fact_schema` from. See [Where the schema comes from](#where-the-schema-comes-from). |

### Exit codes

| Code | Meaning |
|---|---|
| `0` | Every file is valid |
| `1` | At least one issue (structural, a value, or an unknown field) |
| `2` | A rule file, config file or schema could not be loaded |

So a CI step is a single line:

```bash
fluxrules validate rules/*.yaml
```

## evaluate

```bash
fluxrules evaluate rules.yaml event.json
fluxrules evaluate rules.yaml event.json --format json
fluxrules evaluate rules.yaml event.json --schema myapp.models:Payment --validate-facts normalize
```

Loads the rules into an engine, evaluates the event and prints the matched
rules (a table by default, or JSON with `--format json`).

| Option | Meaning |
|---|---|
| `--format table\|json` | Output format. Default `table`. |
| `--engine NAME` | Registered engine to use. Default `PHREAK`. |
| `--schema SPEC` | Fact schema. Rules naming a field it lacks are refused. |
| `--config PATH` | Config file to read `fact_schema` and the comparison settings from. See [Comparison settings](#comparison-settings). |
| `--validate-facts off\|normalize\|strict` | Validate the event against the schema first, as [`validate_facts`](typed-facts.md#normalize-incoming-keys) does. `normalize` accepts `ageDays` for `age_days` and `"5"` for `5`, and flattens a nested event. Needs a schema. Default `off`. |

`evaluate` exits `1` with a one-line message when a rule names an unknown
field, when the event fails validation, or when the engine reports an error
such as a nested event without `--validate-facts` (`FieldNotFoundError`). It
exits `2` when a file or the schema cannot be loaded.

### Comparison settings

`evaluate` applies the comparison settings it finds in the config file, the
same file it reads `fact_schema` from (see
[Where the schema comes from](#where-the-schema-comes-from) for how it is
found):

```yaml
# fluxrules.yaml
strict_null_handling: false     # true: == None matches a None value
strict_type_comparison: false   # true: values of different types are never equal
boolean_string_coercion: false  # true: "true" / "false" are read as booleans
missing_field: unknown          # NOT over a missing field does not fire
uncomparable: unknown           # NOT over "abc" > 5 and the like does not fire
```

Each setting means what the [`EngineConfig`](usage/configuration.md) field of
the same name means, and a setting the file leaves out keeps its default. The
settings apply to whichever engine `--engine` names, including a custom engine
you registered (see [Custom Engines](custom-engines.md)). For
`missing_field`, `false` (with or without quotes) keeps the 1.x behaviour,
`unknown` adopts the 2.0 behaviour, and leaving it out keeps the default.
For `uncomparable`, `false` silences the warning, `unknown` makes such a
comparison unknown, and `raise` stops the command with exit code `1` and a
message naming the field, the operator and both types.
A wrong value, such as `strict_type_comparison: maybe`, stops the command
when the file was named with `--config`. The file's values are read as written
(see [How values are read](yaml-rules.md#how-values-are-read)), so
`strict_type_comparison: yes` is the text `"yes"` and is refused: write `true`
or `false`. In a file found automatically, it is
reported and the file's settings are ignored.

[How FluxRules Compares Values](comparing-values.md) shows exactly which
answers each setting changes.

A comparison that cannot be made, such as `"abc" > 5`, is listed after the
matches. With `--format json` the output has a `comparison_issues` list, each
entry with `field`, `operator`, `fact_type`, `rule_type` and `reason`:

```json
{
  "matched_rules": [],
  "actions": [],
  "comparison_issues": [
    {
      "field": "amount",
      "operator": ">",
      "fact_type": "str",
      "rule_type": "int",
      "reason": "these types cannot be ordered"
    }
  ]
}
```

See [Comparisons that cannot be made](comparing-values.md#comparisons-that-cannot-be-made).

## Fact schemas

### Naming a schema

A schema is named by an import string, in one of two forms:

| Form | Example | Loads |
|---|---|---|
| Module | `myapp.models:Payment` | `Payment` from the module `myapp.models`. The current directory is searched, so a project's own modules work without installing the project. |
| File | `models/payment.py:Payment` | `Payment` from that file. A relative path is resolved against the directory of the file that names it (the rule file or config file), or the current directory for `--schema`. |

The class can be a Pydantic model, dataclass, attrs class, msgspec `Struct` or
`TypedDict`. Nested models are addressed with dotted paths
(`account.age_days`). `--validate-facts` needs a schema Pydantic can validate:
a Pydantic model, dataclass or `TypedDict`.

### Where the schema comes from

For each rule file, the first of these that is present applies:

1. `--schema` on the command line.
2. `fact_schema` in the rule file.
3. `fact_schema` in the config file: `--config PATH`, else
   `$FLUXRULES_CONFIG_FILE`, else the first of `fluxrules.yaml`,
   `fluxrules.yml`, `fluxrules.json`, `config/fluxrules.yaml`,
   `config/fluxrules.yml`, `config/fluxrules.json`, `~/.fluxrules.yaml` and
   `/etc/fluxrules/config.yaml`. These are the same places `DeploymentConfig`
   looks. A `.yaml` or `.yml` file is read as YAML, anything else as JSON.

The config file is read only when neither `--schema` nor the rule file names a
schema. A config file found automatically that cannot be read (for example
because PyYAML is not installed) is skipped with a note; a file passed with
`--config` must be readable.

With none of them, `validate` runs only the structural checks.

### Trusting a schema named in a file

Loading a schema imports its module, and importing runs that module's code. A
schema you name yourself, with `--schema` or in a file you pass with
`--config`, is always loaded. A schema named inside a rule file, or in a
config file found automatically, is loaded only when you add `--trust-schema`:

```bash
fluxrules validate rules/*.yaml --trust-schema
```

Without it, the command stops with exit code `2` and says which file named
which schema, so running `validate` on rule files from someone else never runs
their code by surprise. In CI, where the rule files and the models live in your
own repository, pass `--trust-schema` or name the schema with `--schema`.

```yaml
# fluxrules.yaml
fact_schema: myapp.models:Payment
```

Put the schema in the config when every rule file uses the same model. Put it
in a rule file when files are written against different models. A rule file
that names a schema is tied to that import path, so moving or renaming the
model class means updating those files.

## init

```bash
fluxrules init --dir my-project
```

Writes `rules.json`, `input.json` and `fluxrules.yaml` into the directory,
skipping any that already exist. The config sets the three comparison flags to
their defaults, ready to change (see [Comparison settings](#comparison-settings)),
and includes a commented-out `fact_schema` line to fill in:

```yaml
strict_null_handling: false
strict_type_comparison: false
boolean_string_coercion: false
# fact_schema: myapp.models:Order
```

## serve

```bash
pip install 'fluxrules[api]'
fluxrules serve --host 127.0.0.1 --port 8000 --reload
```

Starts the HTTP API with uvicorn. See [HTTP API Reference](rest-api.md).

## Next Steps

- [From Fact to Action](fact-to-action.md): where these checks sit in the evaluation flow
- [Typed Facts](typed-facts.md#check-rule-files-in-ci): the same checks from Python
- [YAML Rules](yaml-rules.md): the rule file format
- [Example 11: CLI Usage](https://github.com/saurabh2mishra/fluxrules/blob/main/examples/11_cli_usage.py): running the CLI from a script
