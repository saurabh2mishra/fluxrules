# Nested Facts

**Prerequisites:** [Concepts](concepts.md) (Fact) and [Fact Pipeline](fact-pipeline.md).

---

FluxRules engines evaluate flat dictionaries. Use the `Flatten` transform to work with nested fact structures.

## Nested fact structure

```python
fact = {
    "user": {"id": "user_123", "profile": {"country": "US", "tier": "premium"}},
    "transaction": {"amount": 5000, "currency": "USD"},
}
```

## Flattening nested facts

Use `FactPipeline` with `Flatten()` to convert to dot notation:

```python
from fluxrules.pipeline import FactPipeline, Flatten, Require

pipeline = FactPipeline(
    [
        Flatten(),  # Converts nested to dot notation
        Require(["user.id", "transaction.amount"]),  # Validate required fields
    ],
    name="normalize",
)

flat_fact = pipeline(fact)
# Result:
# {
#     "user.id": "user_123",
#     "user.profile.country": "US",
#     "user.profile.tier": "premium",
#     "transaction.amount": 5000,
#     "transaction.currency": "USD"
# }
```

## Writing rules for nested facts

After flattening, write rules using dot notation:

```python
from fluxrules import Rule
from fluxrules.engine.phreak import PhreakEngine

rule = Rule(
    name="premium_users_high_value",
    condition_dsl={
        "type": "group",
        "op": "AND",
        "children": [
            {"type": "condition", "field": "user.profile.tier", "op": "==", "value": "premium"},
            {"type": "condition", "field": "transaction.amount", "op": ">", "value": 10000},
        ],
    },
    action="require_approval",
    persist=False,
)

engine = PhreakEngine()
engine.load_rules([rule])

# Evaluate flattened fact
result = engine.evaluate(flat_fact)
print(f"Matched: {result.fired_rules}")
```

## Full workflow

```python
from fluxrules.pipeline import FactPipeline, Flatten, FieldType, Defaults
from fluxrules.engine.phreak import PhreakEngine

# 1. Define pipeline for nested facts
pipeline = FactPipeline(
    [
        Flatten(),
        Defaults({"user.country": "US"}),  # Fill missing nested fields
        FieldType({"transaction.amount": float}),  # Type coercion on nested fields
    ],
    name="prepare_facts",
)

# 2. Load rules
engine = PhreakEngine()
engine.load_rules([rule])

# 3. Process nested fact
flat = pipeline(fact)

# 4. Evaluate
result = engine.evaluate(flat)
```

---

## Next Steps

- **Fact Pipeline** — See [Fact Pipeline](fact-pipeline.md) for transform details
- **Cross-Fact Rules** — See [Cross-Fact Rules](cross-fact-rules.md) for multi-fact correlation
- **Example** — See [Example 25: Nested Facts](https://github.com/fluxrules/fluxrules/blob/main/examples/25_nested_facts.py)
