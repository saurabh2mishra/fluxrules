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
files as YAML (YAML needs the `yaml` extra). A rule file holds one of:

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

Reports empty conditions, duplicate ids and unsupported operators. With a fact
schema it also reports every field a rule names that the model lacks, each with
a "did you mean" hint, not only the first. Output is JSON:

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
| `1` | At least one issue (structural or unknown field) |
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
| `--config PATH` | Config file to read `fact_schema` from. |
| `--validate-facts off\|normalize\|strict` | Validate the event against the schema first, as [`validate_facts`](typed-facts.md#normalize-incoming-keys) does. `normalize` accepts `ageDays` for `age_days` and `"5"` for `5`, and flattens a nested event. Needs a schema. Default `off`. |

`evaluate` exits `1` with a one-line message when a rule names an unknown
field, when the event fails validation, or when the engine reports an error
such as a nested event without `--validate-facts` (`FieldNotFoundError`). It
exits `2` when a file or the schema cannot be loaded.

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

Importing runs the module's code, so name schemas only in files you trust.

### Where the schema comes from

For each rule file, the first of these that is present applies:

1. `--schema` on the command line.
2. `fact_schema` in the rule file.
3. `fact_schema` in the config file: `--config PATH`, else
   `$FLUXRULES_CONFIG_FILE`, else the first of `fluxrules.yaml`,
   `fluxrules.yml`, `fluxrules.json`, `config/fluxrules.yaml`,
   `config/fluxrules.yml`, `config/fluxrules.json` in the current directory.

With none of them, `validate` runs only the structural checks.

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
skipping any that already exist. The config includes a commented-out
`fact_schema` line to fill in:

```yaml
# fact_schema: myapp.models:Order
```

## serve

```bash
pip install 'fluxrules[api]'
fluxrules serve --host 127.0.0.1 --port 8000 --reload
```

Starts the HTTP API with uvicorn. See [REST API](rest-api.md).

## Next Steps

- [From Fact to Action](fact-to-action.md): where these checks sit in the evaluation flow
- [Typed Facts](typed-facts.md#check-rule-files-in-ci): the same checks from Python
- [YAML Rules](yaml-rules.md): the rule file format
- [Example 11: CLI Usage](https://github.com/saurabh2mishra/fluxrules/blob/main/examples/11_cli_usage.py): running the CLI from a script
