# Runtime Usage Audit: `backend.app.validation`

## 1) High-level module analysis

This audit traces **real execution paths** from runtime entrypoints (FastAPI routes + async validation worker) into `backend/app/validation`.

### Entrypoints traced
- FastAPI app bootstrap includes the `/rules` router. (`app.main`)
- Rule endpoints call `RuleValidationService.validate(...)` during create/update/validate workflows. (`app.api.routes.rules`)
- Async bulk flow calls `submit_bulk_validation(...)` and worker `_run_bulk_validation(...)`, which also invokes `RuleValidationService.validate(...)`. (`app.workers.validation_worker`)

### Real-usage definition applied
A validation file is marked **ACTIVE** only if its logic is executed along those runtime paths.

---

## 2) Dependency graph summary (validation-focused)

### External-to-validation edges (runtime relevant)
- `app.services.rule_validation_service` -> `app.services.brms_service`
- `app.services.brms_service` ->
  - `app.validation._compiled_cache`
  - `app.validation.conflict_detection`
  - `app.validation.dead_rule_detection`
  - `app.validation.duplicate_detection`
  - `app.validation.priority_collision_detection`
  - `app.validation.coverage_analysis`
  - `app.validation.gap_detection`
  - `app.validation.redundancy_detection`
  - `app.validation.sat_validation`
- `app.services.rule_service` -> `app.validation._compiled_cache.invalidate`
- `app.api.routes.rules` -> `app.validation._compiled_cache.invalidate` (cache reset utility)
- `app.workers.validation_worker` -> `app.validation._compiled_cache.invalidate`

### Internal validation edges
- `_compiled_cache` -> `_interval_index`, `conflict_detection` helpers (`_decompose_or_branches`, `_branch_numeric_intervals`)
- `conflict_detection` -> `_normalization`, `_interval_index`
- `_interval_index` -> `_normalization.Interval`
- `coverage_analysis`, `gap_detection`, `redundancy_detection` -> `_normalization`
- `sat_validation` -> `dead_rule_detection`, `redundancy_detection`

---

## 3) File classification table

| File | Classification | Why |
|---|---|---|
| `__init__.py` | STRUCTURAL | Package marker/docstring only. |
| `_compiled_cache.py` | ACTIVE | Called via `BRMSService.validate_candidate(...)` and cache invalidation from services/routes/workers. |
| `_interval_index.py` | ACTIVE | Built/queried by `_compiled_cache` and `ConflictDetector.detect_candidate(...)`. |
| `_normalization.py` | ACTIVE | Used by `conflict_detection` candidate overlap logic that is exercised in route/worker validation path. |
| `conflict_detection.py` | ACTIVE | `ConflictDetector.detect_candidate(...)` is called during candidate validation. |
| `dead_rule_detection.py` | ACTIVE | `DeadRuleDetector.detect(...)` called in `BRMSService.validate_candidate(...)`. |
| `duplicate_detection.py` | ACTIVE | `DuplicateDetector.detect(...)` called in `BRMSService.validate_candidate(...)`. |
| `priority_collision_detection.py` | ACTIVE | `PriorityCollisionDetector.detect(...)` called in `BRMSService.validate_candidate(...)`. |
| `coverage_analysis.py` | PASSIVE | Imported/instantiated in `BRMSService.__init__`, but no runtime calls from traced entrypoints. |
| `gap_detection.py` | PASSIVE | Imported/instantiated, but called only by full `BRMSService.validate(...)` path not reached from traced runtime entrypoints. |
| `redundancy_detection.py` | PASSIVE | Same as above; active only in full validation path/tests. |
| `sat_validation.py` | PASSIVE | Same as above; active only in full validation path/tests. |
| `constraint_graph.py` | POTENTIALLY DEAD — Requires Manual Review | No non-test runtime import/call path found from app entrypoints. |

### Module usage summary
- Total files: **13**
- Active files: **8**
- Passive files: **4**
- Structural files: **1**
- Potentially dead files: **1**

---

## 4) Detailed reasoning per file

### `backend/app/validation/_compiled_cache.py` — ACTIVE
- **Runtime chain**: `POST /rules/validate|create|update` -> `RuleValidationService.validate` -> `BRMSService.validate_candidate` -> `get_compiled_rules_with_index(...)`.
- Also invalidated in write flows via `RuleService` and async worker.
- Note: index is built and returned, but `validate_candidate` currently does not consume the returned `index` variable directly.

### `backend/app/validation/_interval_index.py` — ACTIVE
- Used by `_compiled_cache._build_index(...)` and `ConflictDetector.detect_candidate(...)` to add/query interval overlaps.

### `backend/app/validation/_normalization.py` — ACTIVE
- `constraint_to_interval(...)`, `merge_intervals(...)`, `intervals_by_field(...)` are called by conflict detection in candidate path.

### `backend/app/validation/conflict_detection.py` — ACTIVE
- `ConflictDetector.detect_candidate(...)` is used by `BRMSService.validate_candidate(...)` in all route/worker candidate validations.

### `backend/app/validation/dead_rule_detection.py` — ACTIVE
- `DeadRuleDetector.detect(...)` runs for candidate rule checks in `validate_candidate`.

### `backend/app/validation/duplicate_detection.py` — ACTIVE
- `DuplicateDetector.detect(...)` runs in candidate validation to find candidate-related duplicates.

### `backend/app/validation/priority_collision_detection.py` — ACTIVE
- `PriorityCollisionDetector.detect(...)` is called in candidate validation and filtered to candidate collisions.

### `backend/app/validation/coverage_analysis.py` — PASSIVE
- `CoverageAnalyzer()` is instantiated in `BRMSService.__init__`, but `self.coverage_analyzer` is not invoked by traced runtime routes/workers.

### `backend/app/validation/gap_detection.py` — PASSIVE
- `GapDetector.detect(...)` is only used in `BRMSService.validate(...)` (full validation mode).
- Full mode is not reached from runtime entrypoints traced here; only candidate mode is used.

### `backend/app/validation/redundancy_detection.py` — PASSIVE
- Same rationale as `gap_detection.py`; detector used in full validation path only.

### `backend/app/validation/sat_validation.py` — PASSIVE
- Same rationale as above; SAT checks are in full validation path and not in candidate validation path.

### `backend/app/validation/constraint_graph.py` — POTENTIALLY DEAD — Requires Manual Review
- No runtime importer/caller found in app entrypoints, workers, or services.
- Could be planned/experimental utility; retain until product-owner confirmation.

### `backend/app/validation/__init__.py` — STRUCTURAL
- Package marker only.

---

## 5) Business logic execution map

### Primary sync rule validation path
`FastAPI app (main.py)`
-> `/rules` router
-> `validate_rule` / `create_rule` / `update_rule` endpoints
-> `RuleValidationService.validate(...)`
-> `BRMSService.validate_candidate(...)`
-> validation internals:
- `_compiled_cache.get_compiled_rules_with_index(...)`
- `ConflictDetector.detect_candidate(...)`
- `DeadRuleDetector.detect(...)`
- `DuplicateDetector.detect(...)`
- `PriorityCollisionDetector.detect(...)`

### Primary async bulk validation path
`/rules/bulk/async` endpoint
-> `validation_worker.submit_bulk_validation(...)`
-> background `_run_bulk_validation(...)`
-> `RuleValidationService.validate(...)`
-> same candidate-validation chain as sync path

### Cache invalidation path
Rule write operations
-> `RuleService` / bulk worker / explicit invalidation utility
-> `_compiled_cache.invalidate(...)`

---

## 6) Recommendations for cleanup (safe, non-destructive)

1. **Manual review of `constraint_graph.py`**
   - Confirm whether it is roadmap code. If not needed, deprecate first, then remove in a dedicated change.
2. **Clarify passive full-scan validators** (`coverage_analysis`, `gap_detection`, `redundancy_detection`, `sat_validation`)
   - Either wire to a production endpoint/cron workflow, or document as dormant "full-audit mode" components.
3. **Performance follow-up**
   - In `BRMSService.validate_candidate(...)`, the returned interval `index` from `_compiled_cache` is currently not consumed directly; decide whether to integrate it or remove index construction from this path.
4. **Add runtime observability hooks**
   - Add lightweight counters for candidate/full validation method invocations to distinguish operationally active vs dormant modules over time.
