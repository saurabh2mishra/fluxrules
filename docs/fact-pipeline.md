# Fact Pipeline

**Prerequisites:** [Concepts](concepts.md) (Fact) and [Conditions](conditions.md).

---

A Fact Pipeline transforms facts before rule evaluation. Use pipelines to:

1. **Normalize** - Convert nested structures to flat dicts
2. **Enrich** - Add computed fields
3. **Validate** - Ensure required fields exist
4. **Type coerce** - Convert string values to proper types

## Basic pipeline

```python
from fluxrules import Rule
from fluxrules.engine.phreak import PhreakEngine
from fluxrules.pipeline import Defaults, FactPipeline, Flatten, Rename, FieldType, Require

# Define pipeline stages
pipeline = FactPipeline(
    [
        Flatten(),  # Flatten nested objects (obj.field -> "obj.field")
        Rename({"user_id": ["user.id", "userId"]}),  # Normalize field names
        FieldType({"amount": float}),  # Convert types
        Require(["user_id", "amount"]),  # Validate required fields
    ],
    name="normalize_payment",
)

# Apply to fact
raw_fact = {
    "user": {"id": "user_123"},
    "amount": "5000",  # String needs conversion
    "country": "US",
}

normalized_fact = pipeline(raw_fact)
# Result: {"user_id": "user_123", "amount": 5000.0, "country": "US"}
normalize_pipeline = pipeline

engine = PhreakEngine()
engine.load_rules(
    [
        Rule(
            name="high_value",
            condition_dsl={"type": "condition", "field": "amount", "op": ">", "value": 1000},
            action="review",
            persist=False,
        )
    ]
)

# Now evaluate with engine
result = engine.evaluate(normalized_fact)
```

## Available transforms

| Transform | Purpose | Example |
|-----------|---------|---------|
| `Flatten()` | Nested dict → flat dict with dot notation | `{"user": {"id": 1}}` → `{"user.id": 1}` |
| `Rename()` | Normalize field names | `{"user_id": ["userId", "uid"]}` |
| `FieldType()` | Type coercion | `{"amount": float}` |
| `Defaults()` | Fill missing fields | `{"country": "US"}` |
| `Require()` | Validate required fields | `["amount", "user_id"]` |

## Composition

Pipelines compose with `>>` (sequence) and `|` (fallback):

```python
# Sequence: run clean, then enrich
clean = FactPipeline([Flatten()], name="clean")
enrich = FactPipeline([Defaults({"channel": "web"})], name="enrich")
pipeline = clean >> enrich

# Fallback: try primary, then secondary
primary = FactPipeline([Require(["amount"])], name="primary")
secondary = FactPipeline([Defaults({"amount": 0})], name="secondary")
resilient = primary | secondary

# Apply
try:
    normalized = resilient(raw_fact)
except ValueError as e:
    print(f"Pipeline failed: {e}")
```

## Using pipelines with engines

```python
from fluxrules.pipeline import FactLoader, IterableSource

# Create loader with pipeline
raw_facts = [raw_fact]
loader = FactLoader(
    source=IterableSource(raw_facts),
    pipeline=normalize_pipeline,  # Transform each fact
)

# Evaluate pipeline facts
for normalized_fact in loader:
    result = engine.evaluate(normalized_fact)
    print(f"Matched: {result.fired_rules}")
```

---

## Next Steps

- **Custom Transforms** - See [Custom Transforms](custom-transforms.md) for building domain-specific transforms
- **Example** - See [Example 27: FactPipeline](https://github.com/saurabh2mishra/fluxrules/blob/main/examples/27_factpipeline.py) for complete example
- **Fact Store** - See [Persistence](persistence.md) for storing enriched facts
