# Changelog

FluxRules follows [semantic versioning](https://semver.org/). This page
summarizes each release. The full list of changes, with migration notes, is in
[`CHANGELOG.md`](https://github.com/saurabh2mishra/fluxrules/blob/main/CHANGELOG.md)
in the repository.

**Current release: 1.1.3** (2026-11-04).

## Releases

### 1.1.3 (2026-11-04): Wider comparison tests

No answers change in this release.

- The comparison tests now also cover tuple facts, `evaluate_batch` over
  worker processes, and rules written as `F` expressions or in a YAML file.
  Every path gives the same answer, and
  [How FluxRules Compares Values](comparing-values.md) gains a row for tuples.
- The alpha prefilter uses the engine's own comparison functions, so the two
  cannot drift apart.
- Releases are published to PyPI with trusted publishing, and each file
  carries a digital attestation.

### 1.1.2 (2026-11-03): Every evaluation path agrees

- A single `in` / `not_in` value counts as a one-item list on every path, so
  `isin("US")` no longer matches `"U"`, and a `MembershipValueWarning` tells
  the author to write the list.
- `boolean_string_coercion` works with the alpha prefilter;
  `fluxrules.evaluate()` and the HTTP API follow all comparison settings; and
  `fluxrules evaluate` applies the settings in its config file.
- `PreFilteredEvaluator` no longer drops facts with text, boolean, `Decimal`
  or very large integer values, and its SQL fact store saves `Decimal`, dates
  and tuples exactly.
- New page: [How FluxRules Compares Values](comparing-values.md), generated
  from a test matrix that compares ten evaluation paths.
- `EngineConfig.use_optimized_engine` is deprecated: nothing reads it.

### 1.1.1 (2026-11-02): Documentation reorganized

The library code is unchanged; only the version number moves to 1.1.1.

- Each topic now lives on one page, and the navigation follows the order a
  reader needs it: Getting Started, Using FluxRules, Authoring Rules, The
  Engine, Advanced Guides, Operating, Examples and Reference.
- Duplicate pages are merged. Advanced Capabilities became the
  [Capability Map](advanced-capabilities.md) under Advanced Guides, and links
  every capability to its guide and its example.
- [Concepts](concepts.md) links the Fact section to
  [From Fact to Action](fact-to-action.md) and
  [Ways to Evaluate a Fact](evaluating-facts.md).
- Wrong statements are corrected: facts must be flat, there are no built-in
  actions, sessions do not need the `sql` extra, and `evaluate_with_actions`
  does not run `@action` handlers.
- The [Actions](custom-actions.md) examples handle handler failures, and the
  [Quickstart](quickstart.md) output matches however you run it.
- The docs build fails on any broken link, in CI and before every deploy.
- Removed page addresses: `getting-started/`, `features/`, `usage/` and the
  pages under it, `reference/http-endpoints/`, `action-registry/`,
  `custom-transforms-cheatsheet/` and `custom-transforms-answered/`. Their
  content is on the merged pages above.

### 1.1.0 (2026-11-02): Typed facts, missing-field fixes and batch evaluation

- Engines accept Pydantic models, dataclasses, attrs classes and msgspec
  structs; nested models become dotted keys. See [Typed Facts](typed-facts.md).
- `fact_schema=` checks rule fields against a model when rules load.
  `fields(Model)` gives checked field references, and `lenient_aliases()` and
  opt-in `validate_facts` normalize incoming key styles.
- With a fact schema, `FieldNotFoundError` catches `userAge`, `user_age` and
  `user-age`, not just case variants. It also reports unflattened nested facts.
- `EngineConfig.missing_field` and `MissingFieldNotWarning`: `NOT` over a
  missing field stops firing in 2.0. Opt in now with `"unknown"`.
- `fluxrules validate --schema` checks JSON and YAML rule files against a
  model in CI. The schema can also be named in the rule file or
  `fluxrules.yaml`.
- `fact_pipeline=` runs a `FactPipeline` inside `evaluate()`.
- `engine.evaluate_batch(facts, workers=N)` returns full results in input
  order, with every engine option applied in worker processes.
- Rules compiled with `compile_conditions=True` follow config changes made
  after `load_rules`.
- HTTP API: `POST /api/v1/sessions/{id}/evaluate`, real rule names in
  responses, rule writes no longer stall without Redis, and the explain store
  is bounded.
- New guide: [Ways to Evaluate a Fact](evaluating-facts.md).

### 1.0.2 (2026-10-28): Packaging cleanup

- Python 3.13 and 3.14 support, SPDX license metadata and working README links
  on PyPI.
- `dev` and `docs` moved from extras to dependency groups.

### 1.0.1 (2026-10-28): CLI install hint

- Running `fluxrules` without the `cli` extra prints
  `pip install 'fluxrules[cli]'` instead of a `ModuleNotFoundError`.

### 1.0.0 (2026-10-28): First stable release

- Documented equal-priority ordering: ties go to the highest rule ID. This is
  not a guaranteed contract.

### 0.2.0 (2026-10-20): Fluent condition syntax

- `F("amount") > 5000` expressions build the same condition dicts the engine
  already accepts, combined with `&`, `|` and `~`.
- `FieldNotFoundError` flags a field name that differs from a present key only
  by case.
- `evaluate()` and the engine share one set of operators.
- Fixes for OR rules in the alpha prefilter, uncomparable fact values, and
  action handlers that take `**kwargs`.

### 0.1.4 (2026-10-20): Streaming cache fix and faster AND/OR

- Streaming mode now evicts stale cache entries when a field changes.
- AND and OR trees stop at the first child that decides the result, which
  speeds up selective AND rules by 35 to 45 percent.

### 0.1.3 (2026-10-16): `condition_dsl` renamed to `conditions`

- Breaking: `condition_dsl` became `conditions` everywhere, including YAML
  files and the database column (migration `002`). The `domain/dsl` module
  became `domain/conditions`.
- `Rule(conditions=...)` validates the whole condition tree when the rule is
  created.

### 0.1.2 (2026-10-15): Persistence fixes

- Rule writes through `SQLAlchemyPersistenceAdapter` use one database session
  each, so saved rows are no longer lost.
- `Rule(persist=True)` uses the adapter registered with `ServiceFactory`, so
  it works with PostgreSQL, SQL Server and any other SQLAlchemy database.

### 0.1.1 (2026-10-07)

- Maintenance release with no recorded changes.

### 0.1.0 (2026-10-06): First release intended for publication

- One `EvaluationResult` type across every evaluation path, with
  `fired_rules` as the single name for what matched.
- `Rule(...)` performs no database I/O. `persist` defaults to `False`, and
  `Rule.save()` is the explicit alternative.
- `evaluate()` and `validate()` accept a `Rule`, an iterable of rules, or a
  `Ruleset`.
- `RuleBuilder.build()` returns the canonical `Rule`, and `RuleBuilder` and
  `ConditionBuilder` are exported from the top-level package.

### 0.0.1 (2026-09-14): Initial development version

Never published. It introduced the PHREAK engine with stateless and streaming
modes, Pydantic v2 rule validation, extensible engines, operators, actions and
transforms, the optional FastAPI server and fact pipelines.

## What's next

These items are designed but not yet shipped. The
[backlog](development/backlog.md) explains each one and why it is waiting.

**Planned for 2.0**

- Make `missing_field="unknown"` the default, so `NOT` over a missing field no
  longer fires. 1.1.0 ships the opt-in and a warning that names affected
  fields.
- Safer comparison defaults: a comparison that cannot be made is unknown,
  `True` no longer equals `1`, and types are strict with a fact schema.

**Typed facts**

- A strict mode that raises when a fact lacks a field a rule needs.
- Check rules stored in a database against a fact schema.
- Export a fact schema for rule-editing tools.
- Match rule fields by a model's aliases (for example camelCase).
- Typed facts in the HTTP API and the cross-fact engine.
- Tidy `fluxrules.pipeline.schema`, which still treats Pydantic as optional.

**HTTP API**

- Decide what `evaluation_mode="stateful"` means for stored rules, or remove
  it.
- Make the compiled-rule cache use the configured Redis server.
- Finish or remove the unfinished `/api/v1/engines` endpoints, and clear the
  Redis rule cache when rules change.

## Stability

- **Core API** (`Rule`, the engine, `evaluate()`): stable within 1.x.
- **Condition tree format**: stable.
- **HTTP endpoints**: stable under `/api/v1`. Breaking changes will go under
  `/api/v2`.

[Public API](reference/public-api.md) labels each export with its stability
contract.
