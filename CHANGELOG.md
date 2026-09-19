# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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
