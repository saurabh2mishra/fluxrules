# Changelog

## Version Overview

FluxRules follows semantic versioning.

### Latest Changes

For the most up-to-date changes, see `CHANGELOG.md` in the repository root or the git commit log.

### Key Milestones

- **v1.0.0** (2026) - First stable release
  - Documented equal-priority ordering (rule ID, highest first; not a guaranteed
    contract)
- **v0.2.0** (2026) - Fluent condition DSL
  - `F("amount") > 5000` expressions build the same condition dicts the engine
    already accepts, combined with `&`, `|` and `~`
  - `FieldNotFoundError` flags a field name that differs from a present key only
    by case
  - `evaluate()` and the engine share one set of operators
  - Fixes for OR rules in the alpha prefilter, uncomparable fact values, and
    action handlers that take `**kwargs`
- **v0.1.0** (2026) - First release intended for publication
  - One `EvaluationResult` type across every evaluation path, with
    `fired_rules` as the single name for what matched
  - `Rule(...)` performs no database I/O; `persist` defaults to `False` and
    `Rule.save()` is the explicit alternative
  - `evaluate()` and `validate()` accept a `Rule`, an iterable of rules, or a
    `Ruleset`
  - `RuleBuilder.build()` returns the canonical `Rule`; `RuleBuilder` and
    `ConditionBuilder` are exported from the top-level namespace
- **v0.0.1** (2026) - Initial, unpublished development version
  - PHREAK engine (single engine)
  - Stateless and streaming evaluation modes
  - Pydantic v2 rule validation
  - Extensible engines, operators, actions, and transforms
  - Optional FastAPI REST API
  - Fact pipeline transforms
  - Custom actions system

### Stability

- **Core API**: Stable (Rule, Engine, evaluate())
- **condition tree format**: Stable
- **Endpoints**: Stable under `/api/v1`

### Upgrade path

Breaking changes will be released under `/api/v2` to maintain backward compatibility.

---

## Next Steps

- **Contributing** - See [Contributing](contributing.md)
- **Architecture** - See [Architecture](architecture.md)
