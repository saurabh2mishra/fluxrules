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

## Comparing values

1.1.2 made every evaluation path give the same answer (Phases 0 and 1 of the
comparison plan), and the comparison matrix now also covers tuples,
`evaluate_batch(workers=2)` and rules written with `F` or in YAML. Comparisons
that cannot be made are now reported (`EngineConfig.uncomparable`), and rule
values are checked when rules load (both unreleased).
The items below are the rest of that plan. They are aimed at
**1.2.0**, except the last, which changes defaults and waits for **2.0**.
[How FluxRules Compares Values](../comparing-values.md) shows today's behaviour,
and the comparison matrix (`tests/engine/comparison_matrix.py`) must keep every
path in agreement as each item lands: run `make docs-tables` after any change
to how values compare.

Decisions already made (2026-11-03):

- A comparison that cannot be made keeps its answer (no match) in 1.x, but
  **warns by default**.
- Text that looks like a number is converted **only when a fact schema asks**
  for it, never silently.
- Under `strict_type_comparison`, values of different types are never equal, so
  **`5 != "5"` is a match**. Only ordering (`>`, `<` and the like) across types
  cannot be made.
- Safer defaults wait for 2.0.

### Make common comparisons easy (1.2.0)

**What:**

- **Floats and money:** an `approx` operator, `F("total").approx(0.3)`, using
  `math.isclose` with optional absolute and relative tolerances, plus guidance
  to keep money in `Decimal`.
- **Text:** case-insensitive operators: `equals_ignore_case`,
  `in_ignore_case`, `contains_ignore_case`, `starts_with_ignore_case` and
  `ends_with_ignore_case`, comparing with `str.casefold()`.
- **Dates and numeric text in facts:** with a fact schema and
  `validate_facts="normalize"`, ISO date strings already become dates and
  numeric text becomes numbers. Add tests and a section on the Comparing
  Values page; no conversion happens without a schema (decided above).

Every new operator needs an `F` method, a dict and YAML form, an entry in the
matrix and the reference page, and a sound rule in the alpha prefilter (it may
simply leave the rule unscreened).

**Why waiting:** New operators are new public API, so they belong in a minor
release.

### Safer comparison defaults (2.0)

**What:** Flip the defaults that 1.2.0 makes opt-in:

- `uncomparable="unknown"` by default, so `NOT` never fires because a
  comparison could not be made (alongside `missing_field="unknown"` above);
- `True` no longer equals `1` (a boolean is not a number);
- strict types whenever a fact schema is given.

**Why waiting:** Each one changes which rules fire. Ship the opt-in settings
and warnings in 1.2.0 first, so users can find affected rules before the
defaults change.

## HTTP API

### Define what `evaluation_mode="stateful"` means for stored rules

**What:** Rules stored through the HTTP API have an `evaluation_mode` field
(`"stateless"` by default, or `"stateful"`). It is saved and returned, but no
evaluation path reads it, so a "stateful" rule fires like any other. Either
give it a meaning (for example: such rules run only in a streaming engine or a
session, and the stateless endpoints skip them) or remove the field.

**Why waiting:** Giving it a meaning changes which rules fire for anyone who
set it, and needs a design for where stateful rules run in the HTTP API.
Today's behaviour is documented in [HTTP API Reference](../rest-api.md#post-apiv1rules-login)
and pinned by
`tests/integration/test_e2e_admin_integration.py::TestExistingFeaturesRegression::test_simulate_event_evaluates_stateful_marked_rules`.

### Compiled-rule cache: use the configured Redis server

**What:** `src/fluxrules/services/validation/_compiled_cache.py` connects with
`redis.Redis()`, so it always uses `localhost:6379`, while the rest of the API
reads `REDIS_HOST`, `REDIS_PORT` and `REDIS_DB`. A deployment with Redis on
another host shares rule caches but not compiled rules between processes.
Pass the connection settings in (the module is in `services/`, which must not
import the `api` package), for example through a small setter the API calls
at startup.

**Why waiting:** Behaviour is unchanged from 1.0, and a server without the
cache still works (each process compiles its own rules). Documented in
[Deployment](../deployment.md#redis-optional).

### Finish the `/api/v1/engines` endpoints, and clear the Redis rule cache

**What:** `POST /api/v1/engines/switch` and `/reload` answer "success" but
change nothing; `/benchmark` and `GET /stats` describe a new engine with no
rules. Either make them do what their names say or remove them. Related:
`RuleCache.clear()` in `src/fluxrules/api/engines/adapter.py` empties only the
in-process copy, so with Redis a rule change can take up to the cache's 5
minutes to reach `/api/v1/engines/*` and `/api/v1/rules/simulate`. Clearing
should also delete the Redis keys.

**Why waiting:** Behaviour is unchanged from 1.0 and documented as it is in
[HTTP API Reference: Endpoints that are not finished](../rest-api.md#endpoints-that-are-not-finished),
pinned by `tests/integration/test_engine_endpoints.py`. Removing endpoints or
changing their answers is an API change that needs its own decision.
