# Core Features

FluxRules provides everything needed for production rule engines.

**For in-depth explanations of these features**, see [Core Concepts](concepts.md).

---

## The Essentials

- **One Engine**: [PhreakEngine](concepts.md) — a single lazy, agenda-driven engine with stateless (default) and streaming modes
- **Complex Logic**: [AND/OR/NOT boolean logic](complex-conditions.md) with deep, arbitrary nesting
- **Rule Organization**: [Domains and Tags](domains-and-tags.md) for categorization and filtering
- **Priority-Based Execution**: Higher priority rules fire first when multiple match
- **Multiple Actions**: Each rule can trigger one or more actions in sequence
- **Validation**: [DSL validation](validation-framework.md) catches syntax errors before rules run
- **Explicit IDs**: Auto-generate or provide your own (sequential integers)

---

## Built-In Observability

### Audit Trail (Fired Rules)

Every evaluation returns which rules matched and what actions fired:

```python
from fluxrules.domain import Rule
from fluxrules.engine.phreak import PhreakEngine

engine = PhreakEngine()
rule = Rule(
    name="Check Amount",
    condition_dsl={"type": "condition", "field": "amount", "op": ">", "value": 5000},
    action="flag_for_review",
    persist=False,
)
engine.load_rules([rule])

result = engine.evaluate({"amount": 7500})

print(f"Fired rules: {result.fired_rules}")  # [1]
print(f"Actions: {result.actions}")  # ['flag_for_review']
print(f"Latency: {result.latency_ms}ms")  # [execution time]
```

**Use cases:**
- Compliance audits (show why decision was made)
- Debugging (understand rule behavior)
- User transparency (explain approvals/denials)

**Source:** `src/fluxrules/engine/base.py` - `EvaluationResult` class

---

## What You Get

### Core Library (No Dependencies)

```
fluxrules/
├── domain/       # Rule class, DSL, validation
├── engine/       # PhreakEngine
└── services/     # Evaluators, utilities
```

- Zero external dependencies for core engine
- Pure Python, type-hinted
- Comprehensive error handling and logging

### Optional Features (As Extras)

Install with any combination of extras:

```bash
# Core only
pip install .

# With API server
pip install ".[api]"

# With Prometheus metrics
pip install ".[otel]"

# Everything
pip install ".[all]"
```

See [Installation](installation.md) for the complete list.

---

## Extensibility

### Custom Engines

Implement the engine interface:

```python
from fluxrules.engine.base import BaseEngine


class MyEngine(BaseEngine):
    def evaluate(self, ruleset, facts, filters=None):
        # Your matching algorithm
        return EvaluationResult(...)
```

**Source:** `src/fluxrules/engine/base.py`

### Custom Actions

Actions are any Python callable:

```python python skip
def my_action(fact_id, amount):
    print(f"Processing {fact_id}: ${amount}")


rule = Rule(
    name="process_transaction",
    condition_dsl={"type": "condition", "field": "type", "op": "==", "value": "transaction"},
    action=my_action,  # Any callable
    persist=False,
)
```

---

## Production Ready

- **Type hints** throughout the codebase
- **Comprehensive tests** (2,000+ tests, run with `pytest -m "not performance"`)
- **Error handling** with informative messages
- **Logging** at all levels
- **CI/CD** integration examples in repo

---

## Performance

FluxRules uses lazy PHREAK evaluation (the default) to avoid unnecessary work.
For measured throughput and latency on a stated machine and methodology, see
[Benchmarks](benchmarks.md) and [Load Testing](load-testing.md); do not treat
those figures as guarantees for your workload. To measure your own rules and
facts, run the harness described in [Load Testing](load-testing.md).

---

## Next Steps

- **[Getting Started](quickstart.md)** - Create your first rule
- **[Concepts](concepts.md)** - Understand engines and evaluation
- **[Examples](examples.md)** - Working code demonstrations
