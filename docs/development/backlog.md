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

## HTTP API

### Cap the in-memory explain store (next minor)

**What:** Every evaluation through the HTTP API (`POST /api/v1/evaluate`,
`/api/v1/evaluate/bulk` and `/api/v1/sessions/{id}/evaluate`) saves a record
in `_execution_store`, a plain dict in
`src/fluxrules/api/routes/evaluation.py`, so that
`GET /api/v1/explain/{execution_id}` can find it later. The dict has no size
limit: a long-running server keeps every record until it restarts, and memory
grows with traffic. Keep only the most recent records instead.

**Why waiting:** It needs a decision on the limit and its setting, and its own
tests. It is not a regression: the store has always been unbounded.

**Plan:**

1. Replace the dict with a small bounded store, for example a class in
   `src/fluxrules/api/routes/evaluation.py` built on `collections.OrderedDict`.
   Adding a record past the limit removes the oldest one. Reading a record
   does not change its age (a record's age is when it was evaluated). Guard
   writes with a `threading.Lock`, because FastAPI runs sync routes in a
   thread pool.
2. Keep the same interface the routes use today: `store[execution_id] = record`,
   `execution_id in store` and `store[execution_id]`. Then the three writers
   (`evaluate`, `evaluate_many`) and the reader (`explain`) do not change.
3. Add a setting `EXPLAIN_STORE_MAX_RECORDS` to `src/fluxrules/api/config.py`,
   default `10_000`, read from the environment like the other settings.
   `0` turns the store off (nothing is saved, and `explain` answers `404`
   unless `RuleService.explain` knows the id).
4. Tests, in a new `tests/unit/test_explain_store.py`:
   - with a limit of 3, adding a 4th record removes the 1st;
   - reading a record does not keep it from being removed;
   - a limit of 0 saves nothing;
   - concurrent writes from several threads never exceed the limit.
   And one integration test: with a limit of 2, three evaluations make the
   first `execution_id` answer `404` from `/api/v1/explain/{id}`.
5. Docs: in `docs/rest-api.md`, section `GET /api/v1/explain/{execution_id}`,
   say that the server keeps only the most recent records (10,000 by default,
   set by `EXPLAIN_STORE_MAX_RECORDS`), so an old `execution_id` answers `404`.
   Add the setting to the "Production configuration" section of
   `docs/deployment.md`. Add a CHANGELOG entry under "Changed".

**Cost:** about 40 lines of code and 80 lines of tests. Each evaluation pays
one dict insert and, past the limit, one removal: no measurable change.

**Not in scope:** keeping records across restarts or sharing them between
server processes. That needs a real store (the database or Redis) and is a
separate decision.
