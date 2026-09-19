# Rule Builder

**Prerequisites:** [Concepts](concepts.md) (Rule) and [Conditions](conditions.md) (DSL).

---

The `RuleBuilder` class provides a fluent API for constructing rules step-by-step without manually building DSL dictionaries.

## Basic usage

```python python skip
from fluxrules import Rule
from fluxrules.engine.phreak import PhreakEngine

# Define a rule with all parameters
rule = Rule(
    name="high_value_transaction",
    domain="fraud_detection",
    tags=frozenset(["tier_1", "manual_review"]),
    condition_dsl={"type": "condition", "field": "amount", "op": ">", "value": 5000},
    action="require_approval",
    priority=10,
    persist=False
)

engine = PhreakEngine()
engine.load_rules([rule])
result = engine.evaluate({"amount": 7500})
```

## Fluent API

| Method | Purpose | Returns |
|--------|---------|---------|
| `.name(str)` | Set rule name | Builder |
| `.domain(str)` | Set domain | Builder |
| `.tags(list)` | Set tags | Builder |
| `.condition_dsl(dict)` | Set condition DSL | Builder |
| `.action(str \| tuple)` | Set action(s) | Builder |
| `.priority(int)` | Set priority | Builder |
| `.persist(bool)` | Set persistence flag | Builder |
| `.build()` | Create Rule | Rule |

## Building complex conditions

```python
from fluxrules import Rule
from fluxrules.engine.phreak import PhreakEngine

# Build complex conditions with nested groups
rule = Rule(
    name="complex_rule",
    condition_dsl={
        "type": "group",
        "op": "AND",
        "children": [
            {"type": "condition", "field": "amount", "op": ">", "value": 5000},
            {"type": "condition", "field": "country", "op": "in", "value": ["NG", "GH"]},
        ]
    },
    action="review"
)

engine = PhreakEngine()
engine.load_rules([rule])
result = engine.evaluate({"amount": 6000, "country": "NG"})
print(f"Fired: {result.fired_rules}")
```

## Validation

The builder validates the final rule:

```python python skip
# Demonstration of validation - python skip for demo
try:
    rule = Rule(
        # Missing required fields will raise during creation
        name="test"
        .build()
    )
except ValueError as e:
    print(f"Invalid rule: {e}")
```

---

## Next Steps

- **Rule Lifecycle** — See [Rule Lifecycle](rule-lifecycle.md) for CRUD operations
- **Conditions** — See [Conditions](conditions.md) for DSL operators
- **Example** — See [Example 18: Unified Rule](https://github.com/fluxrules/fluxrules/blob/main/examples/18_unified_rule.py) for working code
