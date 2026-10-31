# Nested Facts

**Prerequisites:** [Concepts](concepts.md) (Fact) and [Fact Pipeline](fact-pipeline.md).

---

FluxRules engines evaluate flat dictionaries. Use the `Flatten` transform to work with nested fact structures,
or pass a model: nested models are flattened for you (see [From a model](#from-a-model)).

A dotted rule field such as `user.profile.country` checked against an
unflattened fact (`{"user": {...}}`) raises `FieldNotFoundError` with a hint to
flatten, rather than silently not matching.

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
from fluxrules import F, Rule
from fluxrules.engine.phreak import PhreakEngine

rule = Rule(
    name="premium_users_high_value",
    conditions=(F("user.profile.tier") == "premium") & (F("transaction.amount") > 10000),
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

## From a model

When facts arrive as Pydantic models, dataclasses, attrs classes or msgspec
structs, pass them to the engine directly. Nested models become dotted keys,
the same shape `Flatten()` produces:

```python
from pydantic import BaseModel

from fluxrules import F, Rule, to_fact_dict
from fluxrules.engine.phreak import PhreakEngine


class Profile(BaseModel):
    country: str
    tier: str


class User(BaseModel):
    id: str
    profile: Profile


user = User(id="user_123", profile=Profile(country="US", tier="premium"))
assert to_fact_dict(user)["profile.country"] == "US"

model_engine = PhreakEngine()
model_engine.load_rules(
    [Rule(id=1, name="us_premium", conditions=F("profile.tier") == "premium", action="flag")]
)
assert model_engine.evaluate(user).fired_rules == [1]
```

Plain `dict` values inside a model are kept as values, not flattened. See
[Typed Facts](typed-facts.md) for checking rules against the model.

## Next Steps

- **Fact Pipeline**: See [Fact Pipeline](fact-pipeline.md) for transform details
- **Cross-Fact Rules**: See [Cross-Fact Rules](cross-fact-rules.md) for multi-fact correlation
- **Example**: See [Example 25: Nested Facts](https://github.com/saurabh2mishra/fluxrules/blob/main/examples/25_nested_facts.py)
