# Public API Reference

**Prerequisites:** [Concepts](../concepts.md), [Quickstart](../quickstart.md).

---

## Stability and Contract Labels

FluxRules has several deliberate contract families. They are coherent because
each family has one entry point and one result shape; they are not intended to
be interchangeable.

| Label | Meaning |
|---|---|
| **Stable** | Supported application-facing API covered by the compatibility tests in `tests/contract/`. |
| **Separate contract** | Supported capability with different semantics and lifecycle; use its dedicated entry point rather than swapping it into the single-fact API. |
| **Experimental** | Available for evaluation, but compatibility and operational behavior may change before 1.0. |
| **Internal** | Implementation detail. It may appear in stack traces or extension code, but applications should not depend on it. |

### Contract map

| Surface | Label | Entry point | Input/output contract |
|---|---|---|---|
| Canonical rule evaluation | **Stable** | `Rule` + `PhreakEngine.load_rules()` + `engine.evaluate(facts)` | Single fact mapping in; infrastructure `EvaluationResult` out (`fired_rules`, `actions`, explanations, metrics). |
| Reference evaluation | **Stable reference** | `ReferenceEvaluator.evaluate(ruleset, facts)` or top-level `fluxrules.evaluate()` | `Ruleset` plus facts in; domain `EvaluationResult` out (`matched_rule_ids`, actions, trace). Used as the oracle for the single-fact subset. |
| Cross-fact correlation | **Separate contract** | `get_cross_fact_engine()` | `insert`/`update`/`retract` fact handles and activation deltas; not a `BaseEngine` replacement. |
| Sessions and persistence | **Separate contract** | `RuleService`, persistence ports, session services | Rulesets and snapshots are managed outside the direct PHREAK matcher. |
| CLI | **Stable adapter** | `fluxrules evaluate`, `validate`, `serve`, `init`, `version` | JSON/file-oriented command contract; uses the canonical public model and reports CLI exit/output semantics. |
| HTTP API | **Stable adapter** | `create_app()` and documented routes | HTTP request/response/error contract; deployment/authentication and optional extras apply. |
| Custom engines/operators/transforms | **Experimental extension** | `BaseEngine`, `register_engine`, operator/transform registries | Extension contracts are tested, but third-party compatibility is not promised before 1.0. |
| `EngineRule`, infrastructure nodes, repositories | **Internal** | Internal conversion/persistence paths | Do not use as the authoring API; `Rule.to_engine_rule()` is the explicit boundary. |

The compatibility guarantee is per row. For example, PHREAK and the reference
evaluator are parity-tested for the supported single-fact DSL subset, while a
Cross-Fact activation delta is intentionally not comparable to a stateless
`EvaluationResult`.

## Top-Level Functions

From `fluxrules`:

- `evaluate(ruleset: Ruleset, facts: dict[str, object]) → EvaluationResult` — Evaluate facts against rules. `facts` may be a plain `dict`, a Pydantic v2/v1 model, or any object with `model_dump()` / `dict()`.
- `validate(ruleset: Ruleset) → list[str]` — Validate rules and return issues
- `explain(execution_id: str) → dict[str, object]` — Get an explanation payload for a past execution; keys: `execution_id`, `matched_rules`, `actions`, `trace`

## Engines

From `fluxrules.engine`:

- `PhreakEngine` (the single production engine, lazy evaluation) — stateless (default) and streaming modes
- `BaseEngine` (abstract base for custom engines)

## Domain Models

From `fluxrules`:

- `Rule` — Pydantic v2 model: `id`, `name`, `domain`, `tags`, `condition_dsl`, `action`, `actions`, `priority`, `enabled`, `persist`
- `Ruleset` — Collection of rules (`group: str`, `rules: tuple[...]`)
- `EvaluationResult` — Result with `ruleset_group`, `matched_rule_ids`, `actions`, `trace`, `execution_id`

## Service Layer

From `fluxrules.services`:

- `RuleService.create()` — Factory for rule management
- `ValidationService()` — Validate rules and conditions
- `EvaluationService()` — Core evaluation
- `PersistenceService()` — Database operations
- `AuditService()` — Track rule executions

## Error Hierarchy

All errors derive from `FluxRulesError`:

```python
from fluxrules import FluxRulesError

try:
    ...
except FluxRulesError as exc:
    logger.error("rule operation failed: %s (%s)", exc, exc.code)
```

| Exception | Base | `code` | Raised when |
|---|---|---|---|
| `FluxRulesError` | `Exception` | `FLUXRULES_ERROR` | Base of the taxonomy; not raised directly |
| `InvalidRuleError` | `FluxRulesError` | `INVALID_RULE` | A rule is structurally unusable |
| `UnknownOperatorError` | `FluxRulesError` | `UNKNOWN_OPERATOR` | A condition names an operator that does not exist |
| `CyclicDependencyError` | `FluxRulesError` | `CYCLIC_DEPENDENCY` | Rule dependencies form a cycle |
| `DSLValidationError` | `InvalidRuleError` | `DSL_VALIDATION_ERROR` | A `condition_dsl` tree fails strict validation |
| `EmptyRuleLogicError` | `InvalidRuleError` | `EMPTY_RULE_LOGIC` | A rule with no condition logic would be stored |
| `LossyConditionRebuildError` | `InvalidRuleError` | `LOSSY_CONDITION_REBUILD` | A DSL tree would be rebuilt from a lossy `.conditions` view |

Each carries a stable `code` intended for logging and API responses. Messages
may be reworded; **codes will not change**.

### `LossyConditionViewWarning`

A `UserWarning` (not an error) emitted when reading `.conditions` on a rule
whose logic uses `OR`/`NOT`/nesting. The leaves are still returned, but the
boolean structure is not in the result — see
[Rule Types](../rule-types.md). To turn it into a hard failure:

```python
import warnings

from fluxrules import LossyConditionViewWarning

warnings.simplefilter("error", LossyConditionViewWarning)
```

## Version

- `fluxrules.__version__`
