# Cross-Fact Rules

**Prerequisites:** [Working Memory](working-memory.md) (fact storage).

---

Correlate multiple facts with cross-fact logic.

## Single-fact limitation

Standard engines evaluate one fact at a time:

```python
from fluxrules.engine.phreak import PhreakEngine

engine = PhreakEngine()
result1 = engine.evaluate({"customer_id": "c1", "amount": 5000})
result2 = engine.evaluate({"customer_id": "c2", "amount": 1000})
# No correlation between result1 and result2
```

## Cross-fact correlation patterns

### Pattern 1: Pre-aggregate upstream

Combine facts before evaluation:

```python
# Combine multiple facts before rule evaluation
combined = {
    "transaction_1_amount": 5000,
    "transaction_2_amount": 3000,
    "total_24h": 8000,  # Pre-computed
    "customer_id": "c1"
}

result = engine.evaluate(combined)
```

### Pattern 2: Multi-step with sessions

Use sessions to accumulate state:

```python
# python skip
from fluxrules.services.rule_service import RuleService

service = RuleService.create()
session = service.create_session()

# Step 1: Check first condition
session.add_fact("transaction_1", {"amount": 5000})
result1 = session.evaluate()

# Step 2: Add second condition
session.add_fact("transaction_2", {"amount": 3000})
result2 = session.evaluate()

# Both facts now in session state
```

### Pattern 3: Working memory

Assert multiple facts and query them:

```python
# Store facts in working memory
id1 = engine.assert_fact({"customer_id": "c1", "amount": 5000})
id2 = engine.assert_fact({"customer_id": "c1", "amount": 3000})

# Evaluate combined logic
result = engine.evaluate({
    "customer_id": "c1",
    "total": 8000,  # Computed from stored facts
})
```

## When to use

- **Multiple related facts** → Aggregate and pass combined dict
- **Multi-step workflow** → Use sessions with fact accumulation
- **Temporal correlation** → Store facts in working memory

---

## Next Steps

- **Working Memory** - See [Working Memory](working-memory.md) for fact storage
- **Sessions** - See [Sessions](sessions.md) for multi-step workflows
- **Examples** - See [Example 24: Cross-Fact Joins](https://github.com/saurabh2mishra/fluxrules/blob/main/examples/24_cross_fact_joins.py)
