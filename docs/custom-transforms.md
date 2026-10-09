# Custom Transforms

**Prerequisites:** [Fact Pipeline](fact-pipeline.md) (Transform basics).

---

Create custom transforms for domain-specific fact enrichment and validation.

## Custom transform structure

```python
from fluxrules.pipeline import Transform, TransformMetadata
from typing import Any


class MyTransform(Transform):
    """Custom transform for fact enrichment."""

    @property
    def metadata(self) -> TransformMetadata:
        return TransformMetadata(
            name="my_transform",
            description="My custom transform",
            category="enrichment",
        )

    def __call__(self, fact: dict[str, Any]) -> dict[str, Any]:
        """Transform the fact."""
        # Your custom logic
        fact["enriched_field"] = "value"
        return fact
```

## Example: Geographic enrichment

```python
from fluxrules.pipeline import Transform, TransformMetadata
import json


class GeoEnricher(Transform):
    """Enrich facts with geographic data."""

    def __init__(self, geo_db: dict[str, dict[str, Any]]):
        self.geo_db = geo_db

    @property
    def metadata(self) -> TransformMetadata:
        return TransformMetadata(
            name="geo_enricher",
            description="Add geographic risk scores",
            category="enrichment",
        )

    def __call__(self, fact: dict[str, Any]) -> dict[str, Any]:
        country = fact.get("country")
        if country and country in self.geo_db:
            enriched = dict(fact)
            enriched["geo_risk_score"] = self.geo_db[country]["risk"]
            enriched["geo_region"] = self.geo_db[country]["region"]
            return enriched
        return dict(fact)
```

## Using custom transforms

```python
from fluxrules.pipeline import FactPipeline

pipeline = FactPipeline(
    [
        GeoEnricher({"NG": {"risk": 8, "region": "Africa"}}),
    ],
    name="enrich_geo",
)

fact = {"country": "NG", "amount": 5000}
enriched = pipeline(fact)
# enriched has geo_risk_score and geo_region added
```

## Error handling

```python
class ValidatingTransform(Transform):
    """Validate and transform."""

    def __call__(self, fact: dict[str, Any]) -> dict[str, Any]:
        if "required_field" not in fact:
            raise ValueError("Missing required_field")

        # Transform
        processed = dict(fact)
        processed["processed"] = True
        return processed

    @property
    def metadata(self) -> TransformMetadata:
        return TransformMetadata(name="validating_transform")


# Pipeline propagates errors
try:
    bad_fact = {"amount": 5000}
    pipeline(bad_fact)
except ValueError as e:
    print(f"Transform failed: {e}")
```

## Composition

Combine custom transforms in pipelines:

```python
enricher = GeoEnricher({"NG": {"risk": 8, "region": "Africa"}})
validator = ValidatingTransform()

# Sequence: enrich then validate
pipeline = enricher >> validator

raw_fact = {"country": "NG", "amount": 5000, "required_field": True}
fact = pipeline(raw_fact)
```

---

## Next Steps

- **Fact Pipeline** - See [Fact Pipeline](fact-pipeline.md) for built-in transforms
- **Example** - See [Example 29: Custom Transforms](https://github.com/fluxrules/fluxrules/blob/main/examples/29_custom_transforms.py)
