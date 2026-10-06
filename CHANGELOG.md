# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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
  (`.domain()`, `.tags()`, `.condition_dsl()`, and a snippet that was not valid
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
