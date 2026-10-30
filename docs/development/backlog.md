# Backlog

Planned work that is designed but not yet shipped. Each item names the release
it is aimed at and why it is waiting. When an item ships, move it to
`CHANGELOG.md` and delete it here.

## Typed facts and missing fields

Shipped in 1.1.0: model input for every engine, `fact_schema=` with load-time
rule checks, `fluxrules.facts.fields()` and `lenient_aliases()`, opt-in
`validate_facts` / `on_invalid`, key-style-insensitive `FieldNotFoundError`, and
`EngineConfig.missing_field` with `MissingFieldNotWarning`. See
[Typed Facts](../typed-facts.md) and
[Missing fields and NOT](../conditions.md#missing-fields-and-not).

### Make `missing_field="unknown"` the default (2.0)

**What:** Flip `EngineConfig.missing_field` from `None` (1.x behaviour plus a
warning) to `"unknown"`, so `NOT` over a missing field no longer fires.

**Why waiting:** It changes which rules fire. 1.1.0 ships the opt-in and a
`MissingFieldNotWarning` so users can find affected rules first.

**Before flipping:**

- Audit stored rulesets (database and YAML) for `NOT` over fields that are
  often absent; the warning names the fields.
- Remove the `None` mode and the warning.
- Update `tests/unit/test_field_not_found.py::TestEvaluateRaisesOnMissingField::test_not_does_not_raise_for_unrelated_absent_field`,
  which pins today's firing behaviour.

### Strict missing-field mode (`strict_fields`)

**What:** An engine option that raises when a fact lacks any field a candidate
rule needs, instead of evaluating the condition as `False`.

**Why waiting:** Multi-schema rulesets legitimately evaluate facts that lack
other schemas' fields, so it needs scoping (per rule, per domain or via
`fact_schema`) before it is useful. Phase 3 of the typed-facts plan.

### `fluxrules check-rules --schema` CLI command

**What:** Check YAML and database rules against a fact schema in CI, using
`fluxrules.facts.schema_info(...).check_rules(...)`, which already exists.

**Why waiting:** Needs a way to name a model class from the command line
(`module:Class`) and a decision on exit codes and output format. Phase 3.

### Schema export for rule-authoring UIs

**What:** Export a fact schema's flat field paths and types (JSON Schema) so
rule editors can offer field pickers and operator choices per type.

**Why waiting:** Depends on the shape the HTTP API wants. Phase 3.

### Rules stored with alias names (`rule_names="alias"`)

**What:** An opt-in mode where `fact_schema` checks and matches rule fields by
the model's aliases (for example camelCase) instead of its Python field names.

**Why waiting:** Only needed if stored rulesets use camelCase field names;
count them first. Migrating stored rules to field names is the alternative.

### Typed facts in the HTTP API and cross-fact engine

**What:** Accept `fact_schema` for engines built by the API engine pool, and
apply `to_fact_dict` / `missing_field` in the cross-fact engine.

**Why waiting:** The HTTP API receives JSON dicts, so model input does not
apply; schema configuration needs an API design. The cross-fact engine does not
evaluate `NOT` today.

### Tidy `fluxrules.pipeline.schema`

**What:** `FactSchema` / `validate_facts` there still treat Pydantic as
optional and point to `fluxrules[api]`, although Pydantic is a core
dependency. Remove the fallback branch and the stale install hint, and consider
building them on `fluxrules.facts`.

**Why waiting:** Cosmetic; no behaviour change.
