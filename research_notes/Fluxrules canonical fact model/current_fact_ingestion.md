# Current Fact Ingestion Path

## Entry Point for Facts into the Engine

### Takeaway
Facts enter the engine through three layered entry points: the top-level `evaluate()` public API, the `RuleService` service layer, and the `BaseEngine.evaluate()` engine-level method. Each layer narrows the accepted types progressively.

### Cited Findings
- `fluxrules.evaluate(rules, facts)` in `src/fluxrules/__init__.py` (line 123) is the highest-level public entry point. It accepts `dict`, a Pydantic v2 model (`.model_dump()`), or a Pydantic v1 model (`.dict()`), and delegates to `_DEFAULT_SERVICE.evaluate_inline()`. — Source: `/Users/saurabhmishra/projects/fluxrules/src/fluxrules/__init__.py`
- `RuleService.evaluate_ruleset(ruleset_id, facts: dict[str, object])` and `RuleService.evaluate_inline(ruleset, facts: dict[str, object])` in `src/fluxrules/services/rule_service.py` (lines 151, 173) are the service-layer entry points. They accept only `dict[str, object]` — Pydantic coercion is handled upstream. — Source: `/Users/saurabhmishra/projects/fluxrules/src/fluxrules/services/rule_service.py`
- `BaseEngine.evaluate(facts: dict[str, Any], filters=None, *, strict_facts=False)` in `src/fluxrules/engine/base.py` (line 175) is the engine-layer entry point. This is for the stateful `PhreakEngine` path (rules loaded separately, facts passed per-call). — Source: `/Users/saurabhmishra/projects/fluxrules/src/fluxrules/engine/base.py`
- The HTTP API entry point is `POST /evaluate` in `src/fluxrules/api/routes/evaluation.py` (line 112). The Pydantic request body `EvaluateRequest.facts` is typed as `dict[str, Any]` — Pydantic coerces the JSON payload automatically. — Source: `/Users/saurabhmishra/projects/fluxrules/src/fluxrules/api/routes/evaluation.py`
- `EnginePort` in `src/fluxrules/engine/interfaces.py` is the Protocol that all engines must satisfy: `evaluate(ruleset: Ruleset, facts: dict[str, object]) -> EvaluationResult`. The `ReferenceEvaluator` (not `BaseEngine`) implements this Protocol. `BaseEngine` has a different call signature (no `Ruleset` argument) and is for the stateful engine path. — Source: `/Users/saurabhmishra/projects/fluxrules/src/fluxrules/engine/interfaces.py`

### Inferences
- There are two distinct engine paths: (1) the `EnginePort`/`ReferenceEvaluator` path used by `RuleService`, which takes a `Ruleset` + `facts` dict per call, and (2) the `BaseEngine`/`PhreakEngine` path which is stateful (rules loaded once, facts passed per evaluation call without a `Ruleset`). A new fact source plugging into the service layer should use path (1).

### Gaps
- None — all entry points are confirmed in source.

---

## Fact Validation and Coercion Before Engine Evaluation

### Takeaway
Pydantic-to-dict coercion happens at two independent locations (public `evaluate()` and `ReferenceEvaluator`). The structural flat-contract validation (`FactValidator`) exists but is opt-in, not enforced on the hot path by default.

### Cited Findings
- `_coerce_facts(facts)` in `src/fluxrules/__init__.py` (line 82–93) converts Pydantic v2 (`.model_dump()`), Pydantic v1 (`.dict()`), or raises `TypeError` for any other non-dict. Plain dicts pass through unchanged. — Source: `/Users/saurabhmishra/projects/fluxrules/src/fluxrules/__init__.py`
- `ReferenceEvaluator.evaluate()` in `src/fluxrules/services/reference_evaluator.py` (lines 53–62) performs the same Pydantic coercion independently. This means the coercion is duplicated between the public API and the evaluator. — Source: `/Users/saurabhmishra/projects/fluxrules/src/fluxrules/services/reference_evaluator.py`
- `FactValidator.validate(source, fact)` in `src/fluxrules/pipeline/validators.py` enforces the structural contract: (1) must be a dict, (2) all keys must be strings, (3) no nested `dict` or `list` values. `None` values are allowed. — Source: `/Users/saurabhmishra/projects/fluxrules/src/fluxrules/pipeline/validators.py`
- `FactValidator` is only invoked by `BaseEngine.evaluate()` when `strict_facts=True` (default is `False`). It is NOT called by `RuleService`, `ReferenceEvaluator`, or the public `evaluate()` function on the hot path. — Source: `/Users/saurabhmishra/projects/fluxrules/src/fluxrules/engine/base.py` lines 195–198
- `FactSchema(BaseModel)` in `src/fluxrules/pipeline/schema.py` is an optional Pydantic-based typed boundary. Its `.to_facts()` method calls `model_dump()` and then `FactValidator.validate()`. It is not wired into any default evaluation path; callers must explicitly use it. — Source: `/Users/saurabhmishra/projects/fluxrules/src/fluxrules/pipeline/schema.py`
- `RuleService.evaluate_inline()` runs `ValidationService.validate_ruleset_detailed()` on the **ruleset** (not the facts) before evaluating. There is no validation of the facts dict in this method. — Source: `/Users/saurabhmishra/projects/fluxrules/src/fluxrules/services/rule_service.py` lines 173–188

### Inferences
- The flat-contract validation exists as a library primitive (`FactValidator`) but is not enforced by default on any evaluation path. A caller who passes nested dicts will not get an error from `RuleService` or the public `evaluate()`; they will simply get `False` for conditions that try to compare a nested dict value against a scalar.
- The duplication of Pydantic coercion between `_coerce_facts()` and `ReferenceEvaluator.evaluate()` suggests the coercion in `ReferenceEvaluator` predates the public API helper.

### Gaps
- None.

---

## Shape of a "Fact" Today

### Takeaway
A "fact" at evaluation time is always a flat `dict[str, Any]` where all keys are strings and values are scalars (int, float, str, bool, None). The type alias `Fact = dict[str, Any]` is defined in `domain/models.py`. Nested structures are structurally forbidden by the pipeline validator contract but not enforced on the default evaluation path.

### Cited Findings
- `Fact = dict[str, Any]` is the canonical type alias defined in `src/fluxrules/domain/models.py` (line 8). — Source: `/Users/saurabhmishra/projects/fluxrules/src/fluxrules/domain/models.py`
- `FactValidator` documents the flat contract explicitly: "no nested dict/list values"; all keys must be strings; `None` values are allowed. This is described as "the engine's minimum contract". — Source: `/Users/saurabhmishra/projects/fluxrules/src/fluxrules/pipeline/validators.py`
- `FactStore` in `src/fluxrules/engine/infrastructure/fact_store.py` stores individual key→scalar pairs (`insert("age", 30)`, `update("age", 31)`). The store's `.facts` property returns `dict[str, Any]` — a flat dict. — Source: `/Users/saurabhmishra/projects/fluxrules/src/fluxrules/engine/infrastructure/fact_store.py`
- `WorkingMemory` in `src/fluxrules/services/execution/working_memory.py` wraps facts as `FactRecord(fact_id, payload: dict[str, Any], revision, inserted_at)`. The `payload` is a plain dict copy. — Source: `/Users/saurabhmishra/projects/fluxrules/src/fluxrules/services/execution/working_memory.py`
- `UnifiedWorkingMemory` in `src/fluxrules/engine/infrastructure/working_memory.py` stores `StoredFact(id, data: dict[str, Any], timestamp, ttl_ms)`. The `assert_fact()` method takes `fact: dict[str, Any]` and copies it. — Source: `/Users/saurabhmishra/projects/fluxrules/src/fluxrules/engine/infrastructure/working_memory.py`
- `EvaluationSession` in `src/fluxrules/services/session.py` accumulates facts via `add_fact(key, value)` and `add_facts(facts: dict)` into a `self.facts: dict[str, Any]` instance variable before calling `evaluate()`. — Source: `/Users/saurabhmishra/projects/fluxrules/src/fluxrules/services/session.py`
- The `Flatten` transform in `src/fluxrules/pipeline/transforms/builtin.py` (line 33) explicitly converts nested dicts to dot-notation keys (`{"user": {"age": 25}}` → `{"user.age": 25}`), confirming that the engine expects a flat dict and that callers with nested data are expected to run `Flatten` first. — Source: `/Users/saurabhmishra/projects/fluxrules/src/fluxrules/pipeline/transforms/builtin.py`

### Inferences
- The `Flatten` transform's existence implies that real-world callers routinely have nested source data, and the intended pattern is: raw (possibly nested) dict → `FactPipeline` with `Flatten` → flat dict → engine.
- There are two notions of "fact" in the codebase: (a) the evaluation-time flat dict passed to `evaluate()`, and (b) the `FactStore`/`WorkingMemory` per-entry model where a single fact is one key→value pair. These are complementary: the evaluation flat dict is the entire bag; the store models individual fact lifecycle.

### Gaps
- There is no documented constraint on value types beyond "not dict, not list". Whether sets, custom objects, or other non-scalar types cause silent failures vs. errors during operator evaluation is not explicitly documented in the source. Operators like `in`, `contains`, etc. in `domain/predicates.py` would work on any Python type, but this is not enforced at the fact-ingestion boundary.

---

## Where a New Fact Source Would Plug In

### Takeaway
A new fact source needs to produce a `dict[str, Any]` and call one of: the public `fluxrules.evaluate()`, `RuleService.evaluate_ruleset()` / `evaluate_inline()`, or go through a `FactPipeline` first if the raw data needs transformation. No registration or interface implementation is required for a basic integration.

### Cited Findings
- The public `evaluate(rules, facts)` in `src/fluxrules/__init__.py` is the simplest integration point. Pass any `dict`, Pydantic model, or object with `.model_dump()`. — Source: `/Users/saurabhmishra/projects/fluxrules/src/fluxrules/__init__.py`
- `RuleService.evaluate_ruleset(ruleset_id, facts)` is the service-layer integration point for persisted rulesets. `RuleService.evaluate_inline(ruleset, facts)` is for transient rulesets. Both accept `dict[str, object]`. — Source: `/Users/saurabhmishra/projects/fluxrules/src/fluxrules/services/rule_service.py`
- `FactPipeline` in `src/fluxrules/pipeline/core.py` is the designated transformation layer between raw source data and engine-ready flat dicts. It is callable: `pipeline(raw_fact) -> dict`. Stock transforms (`Flatten`, `Rename`, `FieldType`, `Defaults`, `Require`) handle normalization. — Source: `/Users/saurabhmishra/projects/fluxrules/src/fluxrules/pipeline/core.py`
- `EvaluationSession.add_fact(key, value)` and `add_facts(facts)` in `src/fluxrules/services/session.py` allow incremental fact accumulation before calling `session.evaluate()`. This is the plug-in point for streaming or event-driven fact sources that need to accumulate partial facts over time. — Source: `/Users/saurabhmishra/projects/fluxrules/src/fluxrules/services/session.py`
- There is no plugin/hook interface for injecting facts directly into the engine's working memory on the `RuleService` path. The `BaseEngine.assert_fact(fact)` method on the `PhreakEngine` path puts a fact into `UnifiedWorkingMemory`, but this path is separate from the `RuleService` / `EnginePort` flow. — Source: `/Users/saurabhmishra/projects/fluxrules/src/fluxrules/engine/base.py` line 127

### Inferences
- For a batch or request/response source, the integration is: produce `dict[str, Any]`, call `evaluate()` or `evaluate_ruleset()`.
- For a streaming source, `EvaluationSession` is the intended API: accumulate with `add_fact()` then call `session.evaluate()`.
- For sources with nested or non-canonical fields, `FactPipeline` with `Flatten`/`Rename`/`FieldType` is the prescribed normalization step.

### Gaps
- There is no documented example of a source that drives `BaseEngine.assert_fact()` directly (the stateful working-memory path). That path's relationship to the service layer is not documented.

---

## Existing Abstractions Related to Facts

### Takeaway
Facts have a rich set of abstractions across three layers: a structural validator, a Pydantic schema boundary, a pipeline transform framework, and two distinct working-memory implementations (one simple/session-scoped, one stateful/engine-scoped).

### Cited Findings
- `EnginePort` Protocol in `src/fluxrules/engine/interfaces.py`: `evaluate(ruleset: Ruleset, facts: dict[str, object]) -> EvaluationResult`. Any object satisfying this protocol is a valid engine. — Source: `/Users/saurabhmishra/projects/fluxrules/src/fluxrules/engine/interfaces.py`
- `Transform` (abstract base class) in `src/fluxrules/pipeline/base.py`: `__call__(fact: dict[str, Any]) -> dict[str, Any]`. Subclass to add a new fact transform step. — Source: `/Users/saurabhmishra/projects/fluxrules/src/fluxrules/pipeline/transforms/builtin.py`
- `FactValidator` in `src/fluxrules/pipeline/validators.py`: static structural checker. `validate(source, fact)` returns the fact unchanged or raises `InvalidFactError`. — Source: `/Users/saurabhmishra/projects/fluxrules/src/fluxrules/pipeline/validators.py`
- `FactSchema(BaseModel)` in `src/fluxrules/pipeline/schema.py`: optional Pydantic base class for typed fact contracts. Subclass with typed fields; call `.to_facts()` to get a validated flat dict. Requires `pydantic`. — Source: `/Users/saurabhmishra/projects/fluxrules/src/fluxrules/pipeline/schema.py`
- `FactStore` in `src/fluxrules/engine/infrastructure/fact_store.py`: key/value store with insert/update/retract semantics, change history, listeners, snapshot/restore, and locking. Used in `PhreakEngine` context. — Source: `/Users/saurabhmishra/projects/fluxrules/src/fluxrules/engine/infrastructure/fact_store.py`
- `WorkingMemory` (session-scoped) in `src/fluxrules/services/execution/working_memory.py`: stores `FactRecord(fact_id, payload: dict, revision, inserted_at)`. Supports `insert_fact`, `update_fact`, `retract_fact`, windowed queries, and field-based queries. — Source: `/Users/saurabhmishra/projects/fluxrules/src/fluxrules/services/execution/working_memory.py`
- `UnifiedWorkingMemory` in `src/fluxrules/engine/infrastructure/working_memory.py`: thread-safe fact store with TTL-based expiry, used by `BaseEngine`. Stores `StoredFact(id, data, timestamp, ttl_ms)`. — Source: `/Users/saurabhmishra/projects/fluxrules/src/fluxrules/engine/infrastructure/working_memory.py`
- `FactPipeline` in `src/fluxrules/pipeline/core.py`: composable transform pipeline. Supports sequence (`>>`), fallback (`|`), and conditional (`when`) composition. — Source: `/Users/saurabhmishra/projects/fluxrules/src/fluxrules/pipeline/core.py`
- `Fact = dict[str, Any]` type alias in `src/fluxrules/domain/models.py` (line 8). — Source: `/Users/saurabhmishra/projects/fluxrules/src/fluxrules/domain/models.py`

### Inferences
- The duplication of working-memory implementations (`WorkingMemory` in `services/execution/` vs. `UnifiedWorkingMemory` in `engine/infrastructure/`) suggests these serve different purposes: the session-scoped one is for the stateful session API; the unified one is for the stateful `BaseEngine`/`PhreakEngine` path.

### Gaps
- No `FactSourcePort` or `FactReaderPort` protocol exists. There is no interface for abstracting where facts *come from* — only where they *go* (the evaluation API). A new fact source has no formal contract to implement.

---

## Rule Evaluation Assumptions About Fact Structure

### Takeaway
All evaluation logic assumes the facts dict is flat: conditions perform a single-level key lookup (`facts[field]`) with no dot-notation traversal. There is no automatic nested-key resolution; dot-notation in field names is a naming convention from the `Flatten` transform, not a path traversal syntax understood by the evaluator.

### Cited Findings
- `ReferenceEvaluator._evaluate_rule()` (line 123): `if condition.fact not in facts: return False` then `evaluate_operator(condition.operator, facts[condition.fact], condition.value)`. Pure flat dict key lookup. — Source: `/Users/saurabhmishra/projects/fluxrules/src/fluxrules/services/reference_evaluator.py`
- `evaluate_dsl()` in `src/fluxrules/domain/dsl/evaluator.py` (line 136–140): `field = dsl.get("field", ""); if field not in facts: return False; return evaluate_operator(dsl.get("op"), facts[field], dsl.get("value"))`. Same flat lookup. — Source: `/Users/saurabhmishra/projects/fluxrules/src/fluxrules/domain/dsl/evaluator.py`
- `RuleCondition.fact` in `src/fluxrules/domain/models.py` (line 41) is typed as `str` — a plain string key, not a path expression. — Source: `/Users/saurabhmishra/projects/fluxrules/src/fluxrules/domain/models.py`
- `exists` DSL node (line 168): `return field in facts and facts[field] is not None`. Flat lookup, no path traversal. — Source: `/Users/saurabhmishra/projects/fluxrules/src/fluxrules/domain/dsl/evaluator.py`
- The `Flatten` builtin transform converts `{"user": {"age": 25}}` to `{"user.age": 25}` with dot notation as a key naming convention. A rule condition referencing `"user.age"` must match that literal string key in the flat dict — the engine does not interpret dots as path separators. — Source: `/Users/saurabhmishra/projects/fluxrules/src/fluxrules/pipeline/transforms/builtin.py`
- Operators in `src/fluxrules/domain/predicates.py` include `in`/`not_in` (membership) and `contains`/`not_contains` (containment). These work on Python's `in` operator, so `in` against a string checks substring; `in` against a list/set checks membership. No special handling for None or missing fields beyond "key not in facts → return False". — Source: `/Users/saurabhmishra/projects/fluxrules/src/fluxrules/domain/predicates.py`

### Inferences
- If a caller passes a nested dict (e.g. `{"user": {"age": 25}}`) and a rule checks `field="user.age"`, the rule will always return False because `"user.age"` is not a key in the top-level dict. The `Flatten` transform must be applied first.
- There is no guard against passing nested dicts on the default path; the rule simply will not match, silently.

### Gaps
- It is unclear whether the `PhreakEngine`'s `_evaluate_rules()` implementation does any additional field dereferencing beyond what the base class provides. That would require reading `src/fluxrules/engine/phreak/_engine.py` (not examined).

---

## Tests Revealing Expected Fact Shape

### Takeaway
Tests consistently construct facts as flat string-keyed dicts. The most common shape is `{"age": 30}`, `{"amount": 5000}`, etc. No test passes nested dicts directly to `evaluate()`.

### Cited Findings
- `test_reference_evaluator.py` (line 19): `ReferenceEvaluator().evaluate(ruleset, {"age": 30})` — flat dict, single string key, integer value. — Source: `/Users/saurabhmishra/projects/fluxrules/tests/unit/test_reference_evaluator.py`
- `test_reference_evaluator.py` (line 43): second test also uses `{"age": 30}`. — Source: `/Users/saurabhmishra/projects/fluxrules/tests/unit/test_reference_evaluator.py`
- `test_fact_store.py` uses `FactStore` with `store.insert("age", 30)` and `store.bulk_insert({"a": 1, "b": 2, "c": 3})` — individual scalar key/value pairs. — Source: `/Users/saurabhmishra/projects/fluxrules/tests/unit/test_fact_store.py`
- `__init__.py` docstring example (line 17): `evaluate(rule, {"age": 30}).fired_rules` — single-key flat dict. — Source: `/Users/saurabhmishra/projects/fluxrules/src/fluxrules/__init__.py`
- `EvaluationSession` docstring example in `session.py`: `session.add_fact("amount", 5000)` — individual key/scalar. — Source: `/Users/saurabhmishra/projects/fluxrules/src/fluxrules/services/session.py`
- `FactValidator` docstring: `FactValidator.validate("MyTransform", {"x": 1, "y": None})` — flat dict, None values explicitly allowed. — Source: `/Users/saurabhmishra/projects/fluxrules/src/fluxrules/pipeline/validators.py`

### Inferences
- The test corpus confirms the flat dict model is not just a contract aspiration — it is how facts are constructed in practice throughout the codebase. No test exercises the Pydantic model path or the `FactSchema` boundary.

### Gaps
- Tests do not cover passing a Pydantic model or `vars(obj)` to `evaluate()` — the Pydantic coercion path (`_coerce_facts`) is present in source but untested in the examined files (may be covered elsewhere).
