# Persistence

**Prerequisites:** [Concepts](concepts.md) (Rule) and [Sessions](sessions.md) (RuleService).

---

FluxRules rules can be persisted to a database. Use persistence when you need to:

1. **Store rules permanently** — survive application restarts
2. **Share rules across instances** — load the same ruleset in multiple processes
3. **Audit trail** — track rule evaluation for compliance

## Quick start: Store and load rules

```python
from fluxrules import Rule
from fluxrules.engine.phreak import PhreakEngine

# Create rules
rules = [
    Rule(
        name="high_value_transaction",
        condition_dsl={"type": "condition", "field": "amount", "op": ">", "value": 5000},
        action="require_approval",
    ),
]

# Load and evaluate with engine
engine = PhreakEngine()
engine.load_rules(rules)
result = engine.evaluate({"amount": 6000})
print(f"Matched rules: {result.fired_rules}")
```

## Persist flag

Every rule has a `persist` flag (default: `True`):

- **`persist=True`** — Rule is stored in the database
- **`persist=False`** — Rule is in-memory only (for testing, temporary rules)

```python
# Persisted rule (stored in database)
rule1 = Rule(
    name="production_rule",
    condition_dsl={"type": "condition", "field": "x", "op": ">", "value": 10},
    action="act",
    persist=True,  # Database storage
)

# Temporary rule (in-memory only)
rule2 = Rule(
    name="test_rule",
    condition_dsl={"type": "condition", "field": "y", "op": "==", "value": "test"},
    action="test_act",
    persist=False,  # No database storage
)
```

## Configuration

Set the database environment during initialization:

```python
from fluxrules.initialization import initialize_persistence

# Development (SQLite, default)
initialize_persistence(env="dev")

# Production (PostgreSQL)
initialize_persistence(env="prod", db_url="postgresql://user:pass@db.example.com/fluxrules")

# Custom URL
initialize_persistence(db_url="postgresql://localhost/my_rules")
```

**Using environment variables:**

```bash
export FLUXRULES_ENV=prod
export FLUXRULES_DB_URL=postgresql://user:pass@db.example.com/fluxrules
```

FluxRules auto-initializes the database on first use if not called explicitly.

## Audit trail

Every rule evaluation produces an audit trail automatically:

```python
from fluxrules import Rule
from fluxrules.engine.phreak import PhreakEngine

# Setup engine and rules
rule = Rule(name="test", condition_dsl={"type": "condition", "field": "amount", "op": ">", "value": 5000}, action="flag")
engine = PhreakEngine()
engine.load_rules([rule])

fact = {"amount": 6000}
result = engine.evaluate(fact)

# Audit trail built-in to result
print(f"Matched: {result.fired_rules}")      # Rule IDs that matched
print(f"Actions: {result.actions}")          # Actions executed
print(f"Time: {result.latency_ms}ms")        # Execution time

# Log for audit
import json
audit_record = {
    "fact_id": fact.get("id"),
    "matched_rules": result.fired_rules,
    "actions": result.actions,
    "latency_ms": result.latency_ms,
}
print(json.dumps(audit_record))
```

Persist audit records to your logging backend as needed.

## Supported databases

- **SQLite** (default, development, single-file)
- **PostgreSQL** (production, scales to 100K+ rules)

---

## Next Steps

- **Sessions** — See [Sessions](sessions.md) for stateful evaluation with persisted rulesets
- **Rule Lifecycle** — See [Rule Lifecycle](rule-lifecycle.md) for rule versioning and deletion
- **Example** — See [Example 05: Persistence](https://github.com/fluxrules/fluxrules/blob/main/examples/05_persistence.py) for evaluation and audit patterns
