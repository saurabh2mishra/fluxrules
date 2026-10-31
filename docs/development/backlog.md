# Backlog

Planned work that is designed but not yet shipped. Each item names the release
it is aimed at and why it is waiting. When an item ships, move it to
`CHANGELOG.md` and delete it here.

## Typed facts and missing fields

Shipped in 1.1.0: model input for every engine, `fact_schema=` with load-time
rule checks, `fluxrules.facts.fields()` and `lenient_aliases()`, opt-in
`validate_facts` / `on_invalid`, key-style-insensitive `FieldNotFoundError`, and
`EngineConfig.missing_field` with `MissingFieldNotWarning`, and schema checks
for JSON/YAML rule files in `fluxrules validate` and `load_rules_from_yaml`. See
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

### Check database rules against a fact schema

**What:** Extend `fluxrules validate --schema` to rules stored through the
persistence layer, as it already does for JSON and YAML rule files.

**Why waiting:** The CLI has no way to point at a database yet (URL option or
the configured persistence layer); that needs deciding first.

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

## Batch evaluation

### `engine.evaluate_batch()` with full results and engine options

**What:** A method on the engine that evaluates many facts and returns one full
`EvaluationResult` per fact (fired rules, actions, explanations, grouping by
domain and tag, latency), in input order:

```python
# python skip: proposed API, not implemented yet
results = engine.evaluate_batch(rows)              # one process
results = engine.evaluate_batch(rows, workers=8)   # eight processes
```

With `workers=1` it loops over `evaluate()`. With more workers, each worker
process rebuilds an engine from this engine's own rules and settings, so
`fact_schema`, `validate_facts`, `on_invalid`, `fact_pipeline` and
`EngineConfig` apply exactly as they do to `evaluate()`. Facts quarantined in
the workers are gathered into the calling engine's `quarantined_facts`.
`fluxrules.engine.runtime.evaluate_batch_parallel` becomes a thin wrapper that
keeps returning fired-rule ids, so existing callers keep working.

**Why waiting:** Today's `evaluate_batch_parallel` builds a plain
`PhreakEngine(streaming_mode=...)` in each worker, so it ignores every other
engine option, and it returns only fired-rule ids. Fixing that changes the
engine's public API and its multiprocessing behaviour, so it needs its own PR,
review and performance run. Open points: settings must be picklable to reach
worker processes (a `Filter` with a lambda is not), which needs a clear early
error; and sending full results back costs more than id lists, which should be
measured before adding any ids-only option.
