# Fact Pipeline

**Prerequisites:** [Concepts](concepts.md) (Fact) and [Conditions](conditions.md).

---

A Fact Pipeline transforms facts before rule evaluation. Use pipelines to:

1. **Normalize**: Convert nested structures to flat dicts
2. **Enrich**: Add computed fields
3. **Validate**: Ensure required fields exist
4. **Type coerce**: Convert string values to proper types

## Pipeline or typed facts?

[Typed facts](typed-facts.md) also clean facts before evaluation. Pick by what
you have:

| You have | Use |
|----------|-----|
| A model class (Pydantic, dataclass, attrs, msgspec) for the fact | Typed facts: `fact_schema=` plus `validate_facts="normalize"` |
| No model, or facts from mixed sources (webhooks, queues, files) | A fact pipeline |
| Computed or default fields, or reusable composed stages (`>>`, `\|`) | A fact pipeline |
| Facts streamed from a source with dead-letter handling | A fact pipeline with `FactLoader` |

With a model, typed facts already cover several transforms. Key-style aliases
replace `Rename`, model coercion replaces `FieldType`, required model fields
replace `Require`, and nested models become dotted keys as with `Flatten`.

The two combine. With both set, the engine runs the pipeline first and then
validates its output against `fact_schema`.

## Basic pipeline

```python
from fluxrules import F, Rule
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
            conditions=F("amount") > 1000,
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

Give the engine the pipeline as `fact_pipeline`, and `evaluate()` applies it to
every fact:

```python
engine = PhreakEngine(fact_pipeline=normalize_pipeline)
engine.load_rules(
    [Rule(name="high_value", conditions=F("amount") > 1000, action="review", persist=False)]
)

result = engine.evaluate(raw_fact)  # normalized, then evaluated
```

- Any callable that takes and returns a fact dict works, not only a
  `FactPipeline`.
- The pipeline runs on dict (and other mapping) input. A model instance is
  already structured, so it skips the pipeline and goes straight to conversion
  and validation.
- A fact the pipeline drops (`Filter`, or a transform whose error policy skips
  the record) returns an empty result. A `Filter` drop is a decision, not an
  error, so the error policy never retries it or replaces it with a fallback.
  Other pipeline errors propagate.
- With `fact_schema=` and `validate_facts`, the pipeline runs first and its
  output is validated.
- `assert_fact()` does not run the pipeline.

To read facts from a source, use `FactLoader` instead:

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

- **Custom Transforms**: See [Custom Transforms](custom-transforms.md) for building domain-specific transforms
- **Typed facts**: See [Example 31: Typed Facts](https://github.com/saurabh2mishra/fluxrules/blob/main/examples/31_typed_facts.py) for a pipeline combined with `fact_schema=` through `fact_pipeline=`
- **Example**: See [Example 27: FactPipeline](https://github.com/saurabh2mishra/fluxrules/blob/main/examples/27_factpipeline.py) for complete example
- **Fact Store**: See [Persistence](persistence.md) for storing enriched facts
