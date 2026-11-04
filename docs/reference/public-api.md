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
| Canonical rule evaluation | **Stable** | `Rule` + `PhreakEngine.load_rules()` + `engine.evaluate(facts)` | One fact in (a mapping or a typed model); `EvaluationResult` out (`fired_rules`, `actions`, `comparison_issues`, explanations, metrics). |
| Reference evaluation | **Stable reference** | `ReferenceEvaluator.evaluate(ruleset, facts)` or top-level `fluxrules.evaluate()` | Rules plus facts in; the same `EvaluationResult` out (`fired_rules`, actions, trace). Used as the oracle for the single-fact subset. |
| Cross-fact correlation | **Separate contract** | `get_cross_fact_engine()` | `insert`/`update`/`retract` fact handles and activation deltas; not a `BaseEngine` replacement. |
| Sessions and persistence | **Separate contract** | `RuleService`, persistence ports, session services | Rulesets and snapshots are managed outside the direct PHREAK matcher. |
| CLI | **Stable adapter** | `fluxrules evaluate`, `validate`, `serve`, `init`, `version` | JSON/file-oriented command contract; uses the canonical public model and reports CLI exit/output semantics. |
| HTTP API | **Stable adapter** | `create_app()` and documented routes | HTTP request/response/error contract; deployment/authentication and optional extras apply. |
| Custom engines/operators/transforms | **Experimental extension** | `BaseEngine`, `register_engine`, operator/transform registries | Extension contracts are tested, but third-party compatibility is not promised before 1.0. |
| `EngineRule`, infrastructure nodes, repositories | **Internal** | Internal conversion/persistence paths | Do not use as the authoring API; `Rule.to_engine_rule()` is the explicit boundary. |

The compatibility guarantee is per row. For example, PHREAK and the reference
evaluator are parity-tested for the supported single-fact condition subset, while a
Cross-Fact activation delta is intentionally not comparable to a stateless
`EvaluationResult`.

## Top-Level Functions

From `fluxrules`:

- `evaluate(rules, facts) → EvaluationResult`: Evaluate facts against rules. `rules` may be a single `Rule`, any iterable of `Rule`, or a `Ruleset`. 
- `facts` may be a plain python `dict` or a model: a Pydantic v2 model, dataclass, attrs class or msgspec `Struct` (a Pydantic v1 model is converted with `.dict()`). Nested models become dotted keys (`customer.age`). See [Typed Facts](../typed-facts.md).
- `to_fact_dict(facts) → dict`: The conversion `evaluate()` and every engine apply to non-dict facts.
- `validate(rules, *, fact_schema=None) → list[str]`: Validate rules and return issues; accepts the same shapes as `evaluate`. Lists structural problems and values that do not suit their operator; with `fact_schema` (a model class), also every field the model lacks and every value of the wrong type for its field. Never raises
- `explain(execution_id: str) → dict[str, object]`: Get an explanation payload for a past execution; keys: `execution_id`, `fired_rules`, `actions`, `trace`

## Engines

From `fluxrules.engine`:

- `PhreakEngine` (the single production engine, lazy evaluation): stateless (default) and streaming modes.
  `evaluate()` accepts a dict or a model. Optional typed-fact keywords:
  `fact_schema=` (check rule fields when rules load), `validate_facts="off" | "normalize" | "strict"`
  and `on_invalid="raise" | "skip" | "quarantine"`; rejected facts are listed in `engine.quarantined_facts`.
  See [Typed Facts](../typed-facts.md). `fact_pipeline=` applies a `FactPipeline`
  (or any dict-to-dict callable) to each fact in `evaluate()` before validation;
  see [Fact Pipeline](../fact-pipeline.md#using-pipelines-with-engines).
  `evaluate_batch(facts, workers=None)` evaluates many facts and returns one
  `EvaluationResult` per fact, in input order; `workers=N` spreads them over `N`
  processes, each rebuilt with the engine's settings. See
  [Many facts at once](../usage/python-api.md#many-facts-at-once).
  A change to the engine's `EngineConfig` object takes effect on its next evaluation,
  for interpreted and compiled rules alike.
- `BaseEngine` (abstract base for custom engines); takes the same typed-fact and `fact_pipeline=` keywords.
  `evaluate_batch` works with `workers=1`; override `_clone_settings()` to allow more.

## Runtime Helpers

From `fluxrules.engine.runtime`:

- `evaluate_batch_parallel(rules, facts, num_workers=None, streaming_mode=False) → list[list[int]]`:
  The older batch helper. Each worker builds a default `PhreakEngine` with
  only `streaming_mode` set, so other engine options (`fact_schema`,
  `fact_pipeline`, `EngineConfig`, ...) do not apply, and it returns only the
  fired rule ids per fact. It keeps working unchanged; for new code use
  `engine.evaluate_batch(facts, workers=N)`, which keeps every option and
  returns full results.
- `DedupEvaluator(engine, backend=LRUDedupBackend())`: Wraps a stateless
  engine and returns a cached result for a fact it has already seen.
  `LRUDedupBackend(max_entries=100_000)` keeps results in memory;
  `RedisDedupBackend` shares them between processes (needs the `redis` extra).
  See [Ways to Evaluate a Fact](../evaluating-facts.md#6-repeated-facts-dedupevaluator).

## Typed Facts

From `fluxrules.facts`:

- `fields(Model)`: Checked field references: `fields(Customer).age >= 18` builds the same condition as `F("age") >= 18`, and a field the model lacks raises `UnknownFieldError`.
- `lenient_aliases()`: Pydantic alias generator accepting snake_case, camelCase, PascalCase, kebab-case and all-lowercase spellings of each field.
- `to_fact_dict(facts)`: Model or mapping to the flat fact dict.
- `schema_info(Model) → FactSchemaInfo`: The flat field paths a rule may reference. `check_rules(rules)` raises on the first unknown field; `unknown_fields(rules)` returns every one as an `UnknownFieldError` (with `.rule`, `.field`, `.suggestion` and `.summary`).
- `load_schema(spec, base_dir=None) → type`: Import a model class from `"package.module:Class"` or `"path/to/models.py:Class"`. See [Check rule files in CI](../typed-facts.md#check-rule-files-in-ci).

From `fluxrules.adapters.loaders`:

- `load_rules_from_yaml(path, fact_schema=None)`: Rule mappings from a YAML file, checked against `fact_schema` or the file's own `fact_schema` key.
- `read_rule_file(path) → RuleFile`: A JSON or YAML rule file as `rules` plus its optional `fact_schema` import string.
- `QuarantinedFact`: Entry in `engine.quarantined_facts` (`facts`, `error`).

## Domain Models

From `fluxrules`:

- `Rule`: Pydantic v2 model: `id`, `name`, `domain`, `tags`, `conditions`, `action`, `actions`, `priority`, `enabled`, `persist`
- `F` (alias of `Field`) and `Condition`: the recommended way to write `conditions`: `(F("amount") > 5000) & (F("country") == "US")`. See [Authoring Rules](../authoring-rules.md). Besides the comparison operators, `F` has `isin`, `not_in`, `contains`, `not_contains`, `starts_with`, `ends_with`, `regex`, `exists`, `approx(value, *, abs_tol=None, rel_tol=None)` for numbers that are close enough, and `equals_ignore_case`, `in_ignore_case`, `contains_ignore_case`, `starts_with_ignore_case` and `ends_with_ignore_case` for text compared without case. See [Conditions](../conditions.md#close-numbers).
- `RuleBuilder`: Fluent authoring; `RuleBuilder.build()` returns a `Rule`. `RuleBuilder.condition()` accepts an `F` expression or a dictionary.
- `ConditionBuilder`: Deprecated in favor of `F`; it will be removed in a future release.
- `Ruleset`: Optional named collection of rules (`group: str`, `rules: tuple[...]`). `evaluate()` accepts bare rules, so you only need this to name a group.
- `EvaluationResult`: The single result type for every evaluation path.
  `fired_rules` is what matched; `actions` are the collected actions. Also
  carries `candidate_rule_ids` (what discovery considered, always a superset of
  `fired_rules`), `ruleset_group`, `trace`, `execution_id`, `latency_ms`,
  `engine_type`, `explanations`, `rules_by_domain`, `rules_by_tag`,
  `fired_segments`.

  `fluxrules.engine.infrastructure.EvaluationResult` is a re-export of this same class, not a second type.

## Service Layer

From `fluxrules.services`:

- `RuleService.create()`: Factory for rule management
- `ValidationService()`: Validate rules and conditions
- `EvaluationService()`: Core evaluation
- `PersistenceService()`: Database operations
- `AuditService()`: Track rule executions

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
| `ConditionValidationError` | `InvalidRuleError` | `DSL_VALIDATION_ERROR` | A `conditions` tree fails strict validation |
| `FieldNotFoundError` | `FluxRulesError` | `FIELD_NOT_FOUND` | A condition's field is missing but a key in the fact is the same name in another key style (`Amount` / `amount`, `userAge` / `user_age`, `user-age`), or the field is a dotted path into a nested value that was not flattened |
| `UnknownFieldError` | `InvalidRuleError`, `AttributeError` | `UNKNOWN_FACT_FIELD` | A rule names a field the engine's `fact_schema` lacks (raised by `load_rules`), or `fields(Model)` is asked for one |
| `RuleValueError` | `InvalidRuleError`, `ValueError` | `RULE_VALUE_TYPE` | A rule value does not fit its field's type in the engine's `fact_schema`, such as `amount: float` compared with `"100.1"` (raised by `load_rules` and `load_rules_from_yaml`); `.field`, `.rule`, `.schema_name`, `.value` and `.summary` hold the details |
| `FactValidationError` | `FluxRulesError`, `ValueError` | `FACT_VALIDATION_ERROR` | With `validate_facts` on and `on_invalid="raise"`, a fact fails validation; `.errors` holds each field location and error code |
| `EmptyRuleLogicError` | `InvalidRuleError` | `EMPTY_RULE_LOGIC` | A rule with no condition logic would be stored |
| `LossyConditionRebuildError` | `InvalidRuleError` | `LOSSY_CONDITION_REBUILD` | A condition tree would be rebuilt from a lossy `.conditions` view |

Each carries a stable `code` intended for logging and API responses. Messages
may be reworded; **codes will not change**.

### `LossyConditionViewWarning`

A `UserWarning` (not an error) emitted when reading `.conditions` on a rule
whose logic uses `OR`/`NOT`/nesting. The leaves are still returned, but the
boolean structure is not in the result; see
[Rule Types](../rule-types.md). To turn it into a hard failure:

```python
import warnings

from fluxrules import LossyConditionViewWarning

warnings.simplefilter("error", LossyConditionViewWarning)
```

### `ComparisonWarning`

A `UserWarning` emitted when a comparison cannot be made and leaves a rule
undecided, such as `"abc" > 5`, `None > 5` or `float("nan") > 5`. The condition
is no match. It is emitted once per process for each field, operator and pair
of types, under the default `EngineConfig(uncomparable=None)`. Set
`uncomparable="false"` to silence it, `"unknown"` so `NOT` over such a
comparison does not fire, or `"raise"` to raise `UncomparableValuesError`
instead. See
[Comparisons that cannot be made](../comparing-values.md#comparisons-that-cannot-be-made).

### `UncomparableValuesError`

Raised under `EngineConfig(uncomparable="raise")` when a comparison cannot be
made and leaves a rule undecided. It is a `FluxRulesError` and a `ValueError`,
with code `UNCOMPARABLE_VALUES`. Its `issue` attribute is the
`ComparisonIssue`. The HTTP API answers it with `422`.

### `ComparisonIssue`

One comparison that could not be made, as listed in
`EvaluationResult.comparison_issues`. A frozen dataclass with `field`,
`operator`, `fact_type`, `rule_type` and `reason`, plus `to_dict()` and
`describe()`. Each field, operator and pair of types is listed once per
evaluation.

### `RuleValueWarning`

A `UserWarning` emitted when a rule is created with a value that does not suit
its operator, so the condition can never match: `>`, `>=`, `<` or `<=` with
`None`, a boolean, a list, a mapping or `NaN`; `starts_with` or `ends_with`
with anything but text; a `regex` that does not compile. Emitted once per
process for each problem. The rule still loads and evaluates as before. See
[Values that suit the operator](../conditions.md#values-that-suit-the-operator).

### `YamlValueWarning`

A `UserWarning` emitted when a YAML rule file or config file holds an unquoted
value that FluxRules 1.1 read differently, such as `NO` (now the text `"NO"`,
1.1 read it as `False`). It names the file and line. See
[How values are read](../yaml-rules.md#how-values-are-read).

### `MembershipValueWarning`

A `UserWarning` emitted when an `in` or `not_in` condition is given a single
value instead of a list, such as `F("country").isin("US")`. The value is
treated as a one-item list (`["US"]`) on every evaluation path, and the warning
names the field and its position in the condition tree. Write the list, or use
`==` / `!=` for a single value, to silence it. See
[Conditions](../conditions.md#collection-membership).

### `MissingFieldNotWarning`

A `FutureWarning` emitted once per `NOT` condition when it fires only because a
field it tests is missing from the fact. In 2.0 such a `NOT` will not fire.
Choose the behaviour now with `EngineConfig(missing_field=...)`: `"unknown"`
adopts the 2.0 behaviour, `"false"` keeps the 1.x behaviour and silences the
warning. See [Conditions](../conditions.md#missing-fields-and-not).

## Version

- `fluxrules.__version__`
