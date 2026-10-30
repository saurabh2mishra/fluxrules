# Pydantic Rule Guide

**Prerequisites:** [Concepts](concepts.md) (Rule) and [Conditions](conditions.md) (condition tree).

---

The `Rule` class is a Pydantic v2 model. This guide covers all fields and validation.

## Rule fields

```python
from fluxrules import F, Rule

rule = Rule(
    # Core (required)
    name="high_value_transaction",
    conditions=F("amount") > 5000,
    
    # Core (optional)
    domain="fraud_detection",                     # Logical grouping (default: "default")
    tags=frozenset(["tier_1", "manual_review"]),  # Searchable keywords
    action="require_approval",                    # Single action (string)
    # action=("act1", "act2"),                   # Multiple actions (tuple)
    priority=10,                                  # Higher = first (default: 0)
    persist=True,                                 # Store in database (default: False)
)
```

### Field Reference

| Field | Type | Required | Default | Notes |
|-------|------|----------|---------|-------|
| `name` | `str` | Yes | none | Human-readable rule name |
| `conditions` | `dict` | Yes | none | Rule logic (condition tree format) |
| `domain` | `str` | No | `"default"` | Organizational grouping |
| `tags` | `frozenset[str]` | No | `frozenset()` | Search/filter keywords |
| `action` | `str \| tuple[str, ...]` | No | `None` | Action(s) when rule fires |
| `priority` | `int` | No | `0` | Evaluation order |
| `persist` | `bool` | No | `False` | Store in the database during construction; see `Rule.save()` |

## Condition tree format

The `conditions` field defines rule logic. Write it with `F` expressions:

```python
from fluxrules import F

# Simple condition
F("amount") > 5000

# AND/OR grouping
(F("amount") > 5000) & (F("country") == "US")

# NOT operator
~(F("verified") == True)
```

Each expression is stored as a dictionary tree. A plain dictionary is accepted
anywhere an `F` expression is, for example when rules come from YAML or a
database:

```python
{
    "type": "group",
    "op": "AND",
    "children": [
        {"type": "condition", "field": "amount", "op": ">", "value": 5000},
        {"type": "condition", "field": "country", "op": "==", "value": "US"},
    ],
}
```

See [Conditions](conditions.md) and [Complex Conditions](complex-conditions.md) for details.

## Validation

Pydantic automatically validates rules:

```python
from pydantic import ValidationError

# Missing required field
try:
    Rule(conditions={...})  # Missing `name`
except ValidationError as e:
    print(f"Validation error: {e}")

# Invalid conditions
try:
    Rule(
        name="test",
        conditions={"type": "invalid", "field": "x"},  # Invalid type
        persist=False
    )
except ValidationError as e:
    print(f"condition validation error: {e}")
```

## Working with fields

### Add tags

```python
# python skip
from fluxrules import F

rule = Rule(
    name="check",
    conditions=F("status") == "pending",
    tags=frozenset(["tier_1", "fraud", "manual_review"]),
    persist=False,
)

# tags are frozenset (immutable)
print(rule.tags)  # frozenset({'tier_1', 'fraud', 'manual_review'})
```

### Multiple actions

```python
from fluxrules import F, Rule

# Action is a single string
rule = Rule(
    name="suspicious",
    conditions=F("risk_score") > 75,
    action="block",  # Single action
    persist=False,
)

print(rule.action)  # "block"
```

### Priority for ordering

```python
from fluxrules import F, Rule

rules = [
    Rule(name="urgent", conditions=F("status") == "critical", priority=100, persist=False),
    Rule(name="normal", conditions=F("status") == "warning", priority=10, persist=False),
    Rule(name="low", conditions=F("status") == "info", priority=1, persist=False),
]

# Higher priority evaluated first
```

!!! note "Equal priorities"
    All matching rules fire; priority only controls order. When two rules share a
    priority (in the same group or in different groups), the engine currently
    orders them by rule ID, highest first. This is an implementation detail, not a
    guaranteed contract, so don't rely on it. Give rules distinct priorities if
    their relative order matters. Same-group, same-priority rules also raise a
    `priority_conflict` validation warning.

## Serialization

Convert Rule to/from JSON:

```python
import json

# To JSON
rule_dict = rule.model_dump()
rule_json = rule.model_dump_json()

# From JSON
restored = Rule(**json.loads(rule_json))
```

---

## Next Steps

- **Conditions**: See [Conditions](conditions.md) for condition operators
- **Validation**: See [Validation Framework](validation-framework.md) for condition validation
- **Rule Lifecycle**: See [Rule Lifecycle](rule-lifecycle.md) for CRUD operations
