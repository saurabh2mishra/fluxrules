# Pydantic Rule Guide

**Prerequisites:** [Concepts](concepts.md) (Rule) and [Conditions](conditions.md) (DSL).

---

The `Rule` class is a Pydantic v2 model. This guide covers all fields and validation.

## Rule fields

```python
from fluxrules import Rule

rule = Rule(
    # Core (required)
    name="high_value_transaction",
    condition_dsl={"type": "condition", "field": "amount", "op": ">", "value": 5000},
    
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
| `name` | `str` | Yes | — | Human-readable rule name |
| `condition_dsl` | `dict` | Yes | — | Rule logic (DSL format) |
| `domain` | `str` | No | `"default"` | Organizational grouping |
| `tags` | `frozenset[str]` | No | `frozenset()` | Search/filter keywords |
| `action` | `str \| tuple[str, ...]` | No | `None` | Action(s) when rule fires |
| `priority` | `int` | No | `0` | Evaluation order |
| `persist` | `bool` | No | `False` | Store in the database during construction; see `Rule.save()` |

## DSL (Condition) format

The `condition_dsl` field defines rule logic:

```python
# Simple condition
{"type": "condition", "field": "amount", "op": ">", "value": 5000}

# AND/OR grouping
{
    "type": "group",
    "op": "AND",
    "children": [
        {"type": "condition", "field": "amount", "op": ">", "value": 5000},
        {"type": "condition", "field": "country", "op": "==", "value": "US"}
    ]
}

# NOT operator
{
    "type": "not",
    "condition": {"type": "condition", "field": "verified", "op": "==", "value": True}
}
```

See [Conditions](conditions.md) and [Complex Conditions](complex-conditions.md) for details.

## Validation

Pydantic automatically validates rules:

```python
from pydantic import ValidationError

# Missing required field
try:
    Rule(condition_dsl={...})  # Missing `name`
except ValidationError as e:
    print(f"Validation error: {e}")

# Invalid DSL
try:
    Rule(
        name="test",
        condition_dsl={"type": "invalid", "field": "x"},  # Invalid type
        persist=False
    )
except ValidationError as e:
    print(f"DSL validation error: {e}")
```

## Working with fields

### Add tags

```python
# python skip
rule = Rule(
    name="check",
    condition_dsl={"type": "condition", "field": "status", "op": "==", "value": "pending"},
    tags=frozenset(["tier_1", "fraud", "manual_review"]),
    persist=False,
)

# tags are frozenset (immutable)
print(rule.tags)  # frozenset({'tier_1', 'fraud', 'manual_review'})
```

### Multiple actions

```python
from fluxrules import Rule

# Action is a single string
rule = Rule(
    name="suspicious",
    condition_dsl={"type": "condition", "field": "risk_score", "op": ">", "value": 75},
    action="block",  # Single action
    persist=False,
)

print(rule.action)  # "block"
```

### Priority for ordering

```python
from fluxrules import Rule

rules = [
    Rule(name="urgent", condition_dsl={"type": "condition", "field": "status", "op": "==", "value": "critical"}, priority=100, persist=False),
    Rule(name="normal", condition_dsl={"type": "condition", "field": "status", "op": "==", "value": "warning"}, priority=10, persist=False),
    Rule(name="low", condition_dsl={"type": "condition", "field": "status", "op": "==", "value": "info"}, priority=1, persist=False),
]

# Higher priority evaluated first
# Ties broken by load order
```

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

- **Conditions** — See [Conditions](conditions.md) for DSL operators
- **Validation** — See [Validation Framework](validation-framework.md) for DSL validation
- **Rule Lifecycle** — See [Rule Lifecycle](rule-lifecycle.md) for CRUD operations
