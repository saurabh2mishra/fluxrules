# Custom Transforms

**Prerequisites:** [Fact Pipeline](fact-pipeline.md) (transforms and pipelines).

---

The built-in transforms (`Flatten`, `Rename`, `FieldType`, `Defaults`,
`Require` and the rest) cover most cleaning work. When you need logic of your
own, such as looking up a risk score or normalizing a phone number, write a
custom transform. This page shows how, and lists the mistakes people make
most often.

## The rule to remember

A pipeline accepts only objects whose class inherits from `Transform`. A plain
function or a class that does not inherit from `Transform` fails when the
pipeline runs, with an `AttributeError`. Subclassing `Transform` is what gives
a step its metadata, its error handling and the `>>` and `|` operators.

## Writing a transform

A transform is a class with two members:

- `__call__(self, fact)`, which takes a fact and returns the new fact.
- `metadata`, a property that describes the transform.

```python
from typing import Any

from fluxrules.pipeline import FactPipeline, Transform, TransformMetadata


class GeoEnricher(Transform):
    """Add a region and a risk score based on the country."""

    def __init__(self, geo_db: dict[str, dict[str, Any]]):
        self.geo_db = geo_db

    @property
    def metadata(self) -> TransformMetadata:
        return TransformMetadata(
            name="geo_enricher",
            description="Add geographic risk scores",
            required_input_fields=["country"],
            output_fields=["geo_risk_score", "geo_region"],
        )

    def __call__(self, fact: dict[str, Any]) -> dict[str, Any]:
        enriched = dict(fact)
        info = self.geo_db.get(fact.get("country"))
        if info:
            enriched["geo_risk_score"] = info["risk"]
            enriched["geo_region"] = info["region"]
        return enriched


pipeline = FactPipeline([GeoEnricher({"NG": {"risk": 8, "region": "Africa"}})], name="enrich_geo")

print(pipeline({"country": "NG", "amount": 5000}))
# {'country': 'NG', 'amount': 5000, 'geo_risk_score': 8, 'geo_region': 'Africa'}
```

`TransformMetadata` takes these fields:

- `name`: a short name, shown in metrics, traces and error messages.
- `description`: a sentence that says what the transform does.
- `required_input_fields`: the fields the transform reads.
- `output_fields`: the fields the transform adds or changes.

Only `name` is required. The field lists are documentation: tools read them
to show what each step needs and produces.

If you leave out `__call__` or `metadata`, Python refuses to create the
object and raises `TypeError: Can't instantiate abstract class`.

## Mixing custom and built-in transforms

A custom transform goes into a pipeline next to the built-in ones:

```python
from fluxrules.pipeline import Defaults, FieldType, Flatten, Rename, Require


class LogStep(Transform):
    """Print the fact and pass it on unchanged."""

    def __init__(self, label: str):
        self.label = label

    @property
    def metadata(self) -> TransformMetadata:
        return TransformMetadata(name="log_step", description=f"Log the fact ({self.label})")

    def __call__(self, fact: dict[str, Any]) -> dict[str, Any]:
        print(f"{self.label}: {fact}")
        return fact


normalize = FactPipeline(
    [
        Flatten(),
        Rename({"user_id": ["user.id", "userId"]}),
        LogStep("after rename"),
        FieldType({"amount": float}),
        Defaults({"country": "US"}),
        Require(["user_id", "amount"]),
    ],
    name="normalize",
)

fact = normalize({"user": {"id": "u_1"}, "amount": "1500"})
# after rename: {'user.id': 'u_1', 'amount': '1500', 'user_id': 'u_1'}
print(fact)
# {'country': 'US', 'user.id': 'u_1', 'amount': 1500.0, 'user_id': 'u_1'}
```

## Rejecting a bad fact

To reject a fact, raise `ValueError` from `__call__`. The pipeline passes the
error on to you, or to its error policy if you set one (see
[Fact Pipeline](fact-pipeline.md)):

```python
class RequirePositiveAmount(Transform):
    @property
    def metadata(self) -> TransformMetadata:
        return TransformMetadata(name="require_positive_amount", required_input_fields=["amount"])

    def __call__(self, fact: dict[str, Any]) -> dict[str, Any]:
        if fact.get("amount", 0) <= 0:
            raise ValueError("amount must be positive")
        return fact


checked = FactPipeline([RequirePositiveAmount()])

try:
    checked({"amount": -5})
except ValueError as e:
    print(f"Rejected: {e}")
```

## Composing transforms

Transforms combine with `>>`, which runs the left side and then the right
side:

```python
enrich_then_check = GeoEnricher({"NG": {"risk": 8, "region": "Africa"}}) >> RequirePositiveAmount()
print(enrich_then_check({"country": "NG", "amount": 5000}))
```

You do not need to wrap each transform in its own `FactPipeline` first.
`a >> b` and `FactPipeline([a, b])` do the same thing.

For branching, use `Conditional` instead of an `if` inside one large
transform. It runs `then_transform` when the predicate is true, and
`else_transform` otherwise:

```python
from fluxrules.pipeline import Conditional

by_source = Conditional(
    predicate=lambda f: f.get("source") == "legacy",
    then_transform=Rename({"id": ["legacy_id"]}),
    else_transform=Rename({"id": ["modern_id"]}),
)

print(by_source({"source": "legacy", "legacy_id": 7}))  # {'source': 'legacy', 'legacy_id': 7, 'id': 7}
```

Each branch stays small, and each one can be tested on its own.

## When you do not need a class

If you only want to apply a function to some fields, `MapValues` does that
without a custom class:

```python
from fluxrules.pipeline import MapValues

clean = FactPipeline([MapValues(str.upper, fields=["country"])])
print(clean({"country": "de", "amount": 10}))  # {'country': 'DE', 'amount': 10}
```

`MapValues(fn, fields=[...])` calls `fn` on the value of each listed field.
Without `fields`, it calls `fn` on every value.

## Saving a pipeline that uses your transform

A pipeline can be saved as a dictionary with `to_dict()` (and from there to
JSON or YAML), then rebuilt with `FactPipeline.from_dict()`. For your
transform to survive that round trip, give it `to_dict` and `from_dict`, and
register the class so the loader can find it by name:

```python
from fluxrules.pipeline import register


class LowercaseEmail(Transform):
    def __init__(self, field: str = "email"):
        self.field = field

    @property
    def metadata(self) -> TransformMetadata:
        return TransformMetadata(name="LowercaseEmail", required_input_fields=[self.field])

    def __call__(self, fact: dict[str, Any]) -> dict[str, Any]:
        out = dict(fact)
        if isinstance(out.get(self.field), str):
            out[self.field] = out[self.field].lower()
        return out

    def to_dict(self) -> dict[str, Any]:
        return {"type": "LowercaseEmail", "field": self.field}

    @classmethod
    def from_dict(cls, spec: dict[str, Any]) -> "LowercaseEmail":
        return cls(field=spec["field"])


register(LowercaseEmail)

saved = FactPipeline([LowercaseEmail(field="email")]).to_dict()
restored = FactPipeline.from_dict(saved)
print(restored({"email": "Ana@Example.COM"}))  # {'email': 'ana@example.com'}
```

## Common mistakes

**Changing the input fact.** Always copy the fact with `dict(fact)` before
you change it. Error policies and retries rely on the original fact staying
as it was:

```python
class AddFlag(Transform):
    @property
    def metadata(self) -> TransformMetadata:
        return TransformMetadata(name="add_flag", output_fields=["flag"])

    def __call__(self, fact: dict[str, Any]) -> dict[str, Any]:
        out = dict(fact)  # copy first, never write to `fact`
        out["flag"] = True
        return out
```

**Assuming a field is present.** `fact["name"]` raises `KeyError` when the
field is missing. Use `fact.get("name")`, or raise `ValueError` on purpose so
the error policy can deal with the fact.

**Passing a plain function.** `FactPipeline([my_function])` fails when the
pipeline runs. Wrap the logic in a `Transform` subclass, or use `MapValues`.

**Empty pipeline.** `FactPipeline([])` raises
`ValueError: Pipeline must have at least one transform`.

## Which approach to use

| You want to | Use |
|---|---|
| Apply a function to some fields | `MapValues(fn, fields=[...])` |
| Pick different steps for different facts | `Conditional(...)` |
| Reject facts that break a rule of yours | A `Transform` that raises `ValueError` |
| Add data from a lookup table or service | A `Transform` that holds the lookup |
| Save the pipeline to JSON or YAML | A `Transform` with `to_dict` and `from_dict`, registered with `register` |

---

## Next Steps

- **Fact Pipeline**: See [Fact Pipeline](fact-pipeline.md) for the built-in transforms, error policies and hooks
- **Example 29**: See [Custom Transforms](https://github.com/saurabh2mishra/fluxrules/blob/main/examples/29_custom_transforms.py) for a runnable script
