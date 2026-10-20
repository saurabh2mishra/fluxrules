# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.2.0] - 2026-10-20

### Added

- **`F` / `Field` fluent condition DSL.** Write conditions as Python expressions:
  `(F("amount") > 5000) & (F("country").isin(["NG", "GH"]))`. Comparison
  operators, `&`, `|` and `~` build the same condition dicts the engine already
  accepts, so stored and YAML rules are unchanged. Named methods cover the
  remaining operators: `isin`, `not_in`, `contains`, `not_contains`,
  `starts_with`, `ends_with`, `regex` and `exists`. `Rule(conditions=...)` and
  `RuleBuilder.condition(...)` accept either an `F` expression or a raw dict.
- **`FieldNotFoundError`** (code `FIELD_NOT_FOUND`). A condition now raises when
  its field is absent from the fact but is a case variant of a key that is
  present, for example `F("Amount")` against `{"amount": 1}`. The message lists
  the available keys and suggests the closest match. Fields that match no
  present key still evaluate to `False`, so rulesets that mix fact schemas keep
  working. `exists()` never raises.
- **Docs.** `docs/conditions.md` is now "Conditions & Rule Authoring": the three
  ways to write conditions, what to keep in mind when authoring, and how to
  validate. README, examples and the other docs use the `F` DSL.

### Fixed

- **OR groups were silently dropped by the alpha prefilter.** The prefilter read a
  `group` or `composite` node's AND/OR selector only from the `logic` key, but the
  engine and the `F` DSL use `op`. A `{"type": "group", "op": "OR"}` rule was
  treated as AND and pruned whenever one branch failed, so it did not fire when
  only one branch matched. This affected dict and YAML rules as well as `F`
  expressions. Both keys are now honored.
- **README install section** now leads with `pip install fluxrules` instead of
  cloning the repository.

### Changed

- **Behavior change:** a condition whose field is a case variant of a present key
  now raises `FieldNotFoundError` instead of returning no match. Rules that
  relied on the silent miss need their field name corrected.
- `ConditionBuilder` is deprecated in favor of `F` and will be removed in a
  future release.

## [0.1.4] - 2026-10-20

### Fixed

- **`NodeMemory.invalidate_field` now correctly evicts streaming cache entries.**
  The inverted index previously keyed on fact *values* (e.g. `30` for `age=30`)
  instead of field *names* (`"age"`), so `invalidate_field("age")` never matched
  any bucket and stale entries remained in the LRU cache indefinitely. A new
  `_key_to_fields` dict stores field names per cache key; `put()` accepts a
  `relevant_fields` kwarg and the engine now supplies it, making invalidation O(k)
  and correct.

### Performance

- **AND/OR condition short-circuit in default interpreter path.**
  `_evaluate_condition_inner` used an eager list comprehension for AND/OR trees,
  forcing all children to evaluate before `all()`/`any()` could exit early. Replaced
  with generator-based evaluation matching the compiled path and the `not` branch.
  Selective AND trees (first condition fails ~85% of the time) show 35–45% throughput
  improvement.

### Added

- **Multi-condition benchmarks** — 6 new scenarios (flat and selective AND trees,
  3–8 conditions/rule) and 3 streaming mode scenarios (unchanged-facts O(1)
  short-circuit, 5–6x speedup) added to `tests/performance/test_benchmark.py`.
- **README `## How it works` section** — evaluation pipeline, Phreak-borrowed
  mechanisms, intentional omissions, and stateless vs. streaming guidance.
- **`compile_conditions` user documentation** — `PhreakEngine.__init__` docstring
  now explains when to enable (3+ selective AND conditions → 20–40% gain) and the
  trade-off on single-condition rules (≈0.90x).
- **Agenda gap documented** — `# NOTE:` comments in `agenda.py` and `_engine.py`
  explain that `add_activation`/`next_activation` are never called from the main
  evaluation path.

## [0.1.3] - 2026-10-16

### Breaking Changes

- **Renamed `condition_dsl` → `conditions`** on `Rule`, `EngineRule`, all API schemas, YAML rule files, and the database column. The old name implied a formal DSL that does not exist; `conditions` is the plain, accurate name. Migrate: replace every `condition_dsl=` kwarg and `"condition_dsl"` dict key with `conditions`. A database migration (`002_rename_condition_dsl_to_conditions`) renames the column; run `alembic upgrade head` after upgrading.
- **Renamed `EngineRule.conditions` (flat tuple) → `condition_nodes`** and `Rule.conditions` property → `condition_nodes`. These were internal derived views; `conditions` now refers to the canonical tree. This only affects code that directly accessed the flat-tuple view.
- **Renamed `domain/dsl/` module → `domain/conditions/`** and all public identifiers within it: `DSLValidationError` → `ConditionValidationError`, `DSLParser` → `ConditionParser`, `DSLNode` → `ConditionTreeNode`, `evaluate_dsl()` → `evaluate_conditions()`, `validate_dsl()` → `validate_conditions()`, and so on. Update any direct imports from `fluxrules.domain.dsl`.

### Changed

- **`Rule(conditions=...)` now validates the full condition tree at construction time.** Previously only a shallow structural check was performed (presence of `"type"` key, non-empty dict). Now `validate_conditions()` runs recursively, catching invalid operators, unknown keys, missing required fields, and empty group children immediately at the authoring point with clear path-scoped error messages. Rules that were silently invalid will now raise `ValidationError` at construction. Three latent bugs in the codebase were found and fixed by this change.
- **`ConditionBuilder.and_group()` / `or_group()` now emit `"op"` instead of `"logic"`.** The `"logic"` key was never a valid condition tree key; it happened to be tolerated by the engine parsers but would fail validation and serialisation. `"op": "AND"/"OR"` is the canonical form. The validator also accepts `"logic"` as a read alias for backward compatibility with any stored data.


## [0.1.2] - 2026-10-15

### Fixed

- **`SQLAlchemyPersistenceAdapter` write methods used a fresh session per operation.**  
  `save_rule`, `update_rule`, and `delete_rule` each accessed the `db` property
  multiple times. Because a plain `sessionmaker` returns a new `Session` on every
  call, `commit()` and `refresh()` operated on an empty second session rather than
  the one that received the ORM object — silently producing no row and falling back
  to a local ID. Each write method now captures `self.db` once at entry.

### Added

- **Multi-provider persistence for `persist=True`.**  
  `Rule(persist=True)` and `Rule.save()` now delegate to the
  `ServiceFactory`-registered adapter when one is present (e.g. PostgreSQL,
  SQL Server, or any SQLAlchemy-supported dialect), falling back to the
  existing `DBConnectionManager` / `initialize_persistence()` path when no
  adapter is registered. This makes `persist=True` respect whatever the
  application configured at startup without any change to call sites.

### Changed

- **`docs/persistence.md`** — new section "Using a different SQL provider"
  with a FastAPI + PostgreSQL example, the adapter priority order, and a note
  that the ServiceFactory path requires schema migrations to be run separately
  (e.g. via Alembic) since it does not call `create_all_tables()`.
- **`docs/dependency-injection.md`** — new "ServiceFactory and persistence"
  section linking the DI setup to the `persist=True` behaviour.
- **`docs/architecture.md`** — replaced the ASCII system-architecture sketch
  with the official diagram (`docs/images/system_architecture.png`).

## [0.1.1] - 2026-10-07

## [0.1.0] - 2026-10-06

First release intended for publication. The changes below tighten the public
API surface so that one concept has one name and one type. `0.0.1` was never
published, so these are breaking relative to an unreleased baseline only and
carry no deprecation shims — carrying a shim for `matched_rule_ids` was
rejected precisely because the name's meaning was the defect.

### Changed — breaking

- **One `EvaluationResult`.** There were two classes of that name: the domain
  one, whose `matched_rule_ids` meant *the rules that fired*, and the engine
  one, whose `matched_rule_ids` meant *the rules discovery considered*. Both
  were exported as `EvaluationResult`, so the same attribute answered a
  different question depending on which function you called, and the engine's
  answer was a superset that silently over-reported matches. They are now a
  single class owned by `fluxrules.domain.models`;
  `fluxrules.engine.infrastructure.EvaluationResult` re-exports it.
- **`fired_rules` is the only name for what matched.** `matched_rule_ids` is
  removed from the attribute set, the constructor, and the persisted schema.
  `candidate_rule_ids` remains the discovery prefilter's output and is
  guaranteed to be a superset of `fired_rules` on every evaluation path,
  including the reference evaluator.
- **`Rule(...)` no longer touches the database.** `persist` now defaults to
  `False`, so constructing a rule is a pure in-memory operation; previously the
  default `True` meant importing a module that defined rules opened a
  connection and created a `.db` file, then swallowed any failure as a log
  warning. Persist explicitly with the new `Rule.save()` or `persist=True`.
  The redundant `except Exception` around persistence is gone —
  `PersistenceManager.persist_rule` already degrades to a local ID, so anything
  escaping it is a real fault.
- **`RuleBuilder.build()` returns `Rule`**, not the internal `EngineRule`, so a
  built rule goes straight into `load_rules()` or `evaluate()`. Use the new
  `build_engine_rule()` for the internal representation. `RuleBuilder`'s
  `persist` default is now `False` to match `Rule`.
- **`evaluate()` and `validate()` take rules directly.** Both accept a single
  `Rule`, any iterable of `Rule`, or a `Ruleset`; the first parameter is
  renamed `ruleset` → `rules`. Building a `Ruleset` of `to_engine_rule()`
  conversions is no longer required to evaluate a list of rules.
- **`explain()` returns `fired_rules`** instead of `matched_rules`, matching
  `EvaluationResult`. The HTTP API's own `matched_rules` response field is a
  separate wire contract and is unchanged.
- The `evaluation_results` table's `matched_rule_ids` column is now
  `fired_rules`. The table is created by `create_all()` rather than Alembic, so
  an existing development database needs to be recreated.

### Fixed

- `RuleBuilder()` with no explicit ID allocated from a second, builder-local
  sequential generator that also started at 1, so the first built rule and the
  first directly-constructed rule were assigned the same ID and evaluating them
  together failed with "Ruleset has duplicate rule ids". The builder now defers
  to the same shared generator `Rule` uses.
- `docs/rule-builder.md` documented a `RuleBuilder` API that did not exist
  (`.domain()`, `.tags()`, `.conditions()`, and a snippet that was not valid
  Python) while never demonstrating the real builder. Every block on the page
  is now executable and covered by the documentation harness.

### Added

- `Rule.save()` — explicit persistence for a rule built in memory.
- `RuleBuilder`, `ConditionBuilder`, and the `Rules` input alias are exported
  from the top-level `fluxrules` namespace.
- `RuleBuilder.build_engine_rule()` for the internal `EngineRule` shape.
- A quickstart contract test (`tests/contract/test_quickstart_contract.py`) that
  runs the documented ten-line example in a clean subprocess, asserts it emits
  no warnings, and asserts it writes nothing to disk. CI runs it as its own step
  ahead of the main suite so a broken first-run experience fails loudly.

## [0.0.1] - 2026-09-14

Initial, unpublished development version. FluxRules is a Python rule-evaluation
library built on a single engine, PHREAK, with stateless (default) and streaming
evaluation modes.

### Added

- Core evaluation API — `evaluate()`, `validate()`, `explain()` over a typed
  `Ruleset` of rules, with a curated public `__all__` and a shipped `py.typed`
  marker.
- PHREAK engine (`PhreakEngine`): lazy, agenda-driven evaluation in stateless
  (default) and streaming modes. Correctness is checked against the
  dependency-free `ReferenceEvaluator` oracle and by stateless/streaming parity.
- Condition operators — 13 distinct operators plus 6 word aliases: `==`/`eq`,
  `!=`/`ne`, `>`/`gt`, `>=`/`gte`, `<`/`lt`, `<=`/`lte`, `in`, `not_in`,
  `contains`, `not_contains`, `starts_with`, `ends_with`, `regex`; combined with
  arbitrary AND/OR/NOT nesting.
- Extensibility — public `register_engine()` / `unregister_engine()` (a custom
  `BaseEngine` becomes selectable via `get_engine()`, the HTTP API, and the CLI
  `--engine` flag; the built-in engine is protected), registries for custom
  operators/actions/transforms/validators, entry-point auto-discovery
  (`fluxrules.plugins.discovery.load_plugins`), and a public conformance kit
  (`fluxrules.testing.assert_engine_contract`).
- Fact pipeline — `Flatten`, `Rename`, `Defaults`, `Require`, `FieldType`, and
  user-defined transforms.
- Validation framework (structure, conflicts, dead/redundant rules) and an audit
  trail with integrity hashing.
- Optional adapters behind extras: FastAPI HTTP API (`api`), SQLAlchemy/Alembic
  persistence (`sql`), Redis sessions (`redis`), OpenTelemetry (`otel`), YAML
  rules (`yaml`), and a Typer CLI (`cli`).
- Documentation (MkDocs Material), 31 runnable examples, a suite of 2,000+ tests,
  and a CI-gated scale test.

### Security

- Scoped flake8-bandit (`S`) ruff rule set enforced in the lint gate
  (exec/eval/pickle/marshal/weak-hash/SQL-injection/try-except-pass).
- CI security job (`bandit` + `pip-audit`) and a pull-request `dependency-review`
  job; SPDX SBOM generation and Sigstore signing in the release workflow.
- `SECURITY.md` (supported versions, response targets, coordinated disclosure), a
  threat model in `docs/security.md`, `CODEOWNERS`, and branch-protection
  guidance in `CONTRIBUTING.md`.
