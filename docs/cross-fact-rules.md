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

A session keeps the fields you add across steps. Add a running total as each
transaction arrives, and evaluate after every step:

```python
from fluxrules import F, Rule
from fluxrules.domain.models import Ruleset
from fluxrules.services.rule_service import RuleService

service = RuleService.create()
velocity = [Rule(id=1, name="high_24h_total", conditions=F("total_24h") > 6000, action="review")]
service.persist(
    Ruleset(group="velocity", rules=tuple(r.to_engine_rule(group="velocity") for r in velocity))
)
session = service.create_session("velocity")

# Step 1: the first transaction (5000) arrives
session.add_fact("total_24h", 5000)
assert session.evaluate().fired_rules == []

# Step 2: a second transaction (3000) arrives; update the running total
session.add_fact("total_24h", 8000)
assert session.evaluate().fired_rules == [1]
```

Your code computes the total; the session only remembers it between steps.
Rules read flat fields, so store values such as `total_24h` rather than whole
transactions under one key.

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

- **Working Memory**: See [Working Memory](working-memory.md) for fact storage
- **Sessions**: See [Sessions](sessions.md) for multi-step workflows
- **Examples**: See [Example 24: Cross-Fact Joins](https://github.com/saurabh2mishra/fluxrules/blob/main/examples/24_cross_fact_joins.py)
