# Your Question Answered: Custom Transforms in FactPipeline

This document directly answers your question about what happens when you want to pass your own transformation function or class instead of built-in transforms like `Flatten()`.

---

## Your Question

> In this example from `fluxrules.pipeline` import `FactPipeline`, `Flatten`, `Rename`, `FieldType`, `Defaults`, `Require`... what happen if a user want to pass his own transformation function or class instead of `Flatten()`. How can FactPipeline accept these or what happens if all custom functions or class needed to be passed within FactPipeline.

---

## The Answer: 4-Point Summary

### 1. **Plain Functions Don't Work**

```python skip
# ❌ This will FAIL
from fluxrules.pipeline import FactPipeline


def my_flatten(fact):
    return {k.replace("_", "."): v for k, v in fact.items()}


normalize = FactPipeline([my_flatten])
# → AttributeError: 'function' object has no attribute 'metadata'
```

**Why?** FactPipeline expects all transforms to have a `.metadata` property, which only exists on `Transform` classes.

### 2. **Plain Classes Don't Work**

```python skip
# ❌ This will FAIL
from fluxrules.pipeline import FactPipeline


class MyFlatten:
    def __call__(self, fact):
        return {k.replace("_", "."): v for k, v in fact.items()}


normalize = FactPipeline([MyFlatten()])
# → AttributeError: 'MyFlatten' object has no attribute 'metadata'
```

**Why?** Same reason-they don't inherit from `Transform` and don't have `.metadata`.

### 3. **Classes Inheriting from Transform Work Perfectly**

```python
# ✅ This WORKS
from fluxrules.pipeline import FactPipeline, Flatten, Require, Transform, TransformMetadata


class MyFlatten(Transform):
    def __call__(self, fact):
        return {k.replace("_", "."): v for k, v in fact.items()}

    @property
    def metadata(self):
        return TransformMetadata(name="MyFlatten")


normalize = FactPipeline([MyFlatten()])  # ✓ Works!
```

**Why?** Because your class now:
- Inherits from `Transform`
- Implements `__call__` (makes it callable)
- Implements `metadata` property (publishes transform contract)

### 4. **FactPipeline is Designed to Accept Custom Classes**

The framework is **designed** to let you write your own transforms. Built-in transforms like `Flatten()`, `Rename()`, etc. are just examples-they're all `Transform` subclasses too!

```python
# All of these are Transform subclasses
from fluxrules.pipeline import Flatten, Rename

Flatten()  # ← Built-in
Rename({"user_id": ["user.id"]})  # ← Built-in
MyFlatten()  # ← Your class (same pattern!)
```

---

## The Complete Pattern

Here's what your custom transform needs to be accepted by FactPipeline:

```python
from fluxrules.pipeline import Transform, TransformMetadata
from typing import Any


class YourTransform(Transform):
    """Your transform description."""

    # 1. Define __init__ if you need configuration
    def __init__(self, config_param: str) -> None:
        self.config_param = config_param

    # 2. Implement __call__ to transform facts
    def __call__(self, fact: dict[str, Any]) -> dict[str, Any]:
        # Process the fact
        out = dict(fact)  # Always create a copy!
        # ... your transformation logic ...
        return out

    # 3. Implement metadata property
    @property
    def metadata(self) -> TransformMetadata:
        return TransformMetadata(
            name="YourTransform",  # Required
            version="1.0.0",  # Recommended
            required_input_fields=["field"],  # Optional but good to have
            output_fields=["output_field"],  # Optional but good to have
            errors_raised=[ValueError],  # Optional but important for error handling
            description="What it does",  # Optional but helpful
        )
```

That's it! Now you can use it in your pipeline:

```python
pipeline = FactPipeline(
    [
        Flatten(),
        YourTransform(config_param="value"),  # ← Your custom transform
        Require(["field"]),
    ]
)
```

---

## Three Real-World Examples

### Example 1: Simple Field Validation

```python
class ValidateEmail(Transform):
    """Validate email format."""

    def __init__(self, field: str = "email"):
        self.field = field

    def __call__(self, fact):
        email = fact.get(self.field)
        if not email or "@" not in email:
            raise ValueError(f"Invalid email: {email}")
        return fact  # Pass through if valid

    @property
    def metadata(self):
        return TransformMetadata(
            name="ValidateEmail",
            required_input_fields=[self.field],
            errors_raised=[ValueError],
        )


# Use it
pipeline = FactPipeline([ValidateEmail(), Require(["email"])])
```

### Example 2: Enrichment with External Data

```python
class EnrichCountry(Transform):
    """Look up country details from a database."""

    def __init__(self, db: dict):
        self.db = db

    def __call__(self, fact):
        code = fact.get("country_code")
        if not code or code not in self.db:
            raise KeyError(f"Unknown country: {code}")

        details = self.db[code]
        out = dict(fact)
        out["country_name"] = details["name"]
        out["region"] = details["region"]
        return out

    @property
    def metadata(self):
        return TransformMetadata(
            name="EnrichCountry",
            required_input_fields=["country_code"],
            output_fields=["country_name", "region"],
            errors_raised=[KeyError],
        )


# Use it
countries = {
    "US": {"name": "United States", "region": "Americas"},
    "NG": {"name": "Nigeria", "region": "Africa"},
}

pipeline = FactPipeline([EnrichCountry(db=countries), Require(["country_name"])])
```

### Example 3: Complex Data Transformation

```python
class NormalizePhoneNumber(Transform):
    """Normalize phone numbers to a standard format."""

    def __init__(self, field: str = "phone", country_code: str = "US"):
        self.field = field
        self.country_code = country_code

    def __call__(self, fact):
        phone = fact.get(self.field)
        if not phone:
            return fact  # Skip if missing

        # Remove non-digits
        digits = "".join(c for c in str(phone) if c.isdigit())

        if self.country_code == "US" and len(digits) == 10:
            # Format as (XXX) XXX-XXXX
            normalized = f"({digits[:3]}) {digits[3:6]}-{digits[6:]}"
        else:
            normalized = digits

        out = dict(fact)
        out[self.field] = normalized
        return out

    @property
    def metadata(self):
        return TransformMetadata(
            name="NormalizePhoneNumber",
            required_input_fields=[self.field],
            output_fields=[self.field],
        )


# Use it
pipeline = FactPipeline(
    [
        NormalizePhoneNumber(field="phone", country_code="US"),
        ValidateEmail(),
    ]
)
```

---

## What About Serialization?

If you want to save your pipeline to YAML/JSON and load it back, your transform needs `to_dict()` and `from_dict()`:

```python
class MyTransform(Transform):
    def __init__(self, field: str):
        self.field = field

    def __call__(self, fact):
        # ... implementation ...
        return fact

    @property
    def metadata(self):
        return TransformMetadata(name="MyTransform", required_input_fields=[self.field])

    # Add these two methods for serialization
    def to_dict(self) -> dict[str, Any]:
        return {"type": "MyTransform", "field": self.field}

    @classmethod
    def from_dict(cls, spec: dict[str, Any]) -> "MyTransform":
        return cls(field=spec["field"])


# Register it so FactPipeline can find it
from fluxrules.pipeline import register

register(MyTransform)

# Now serialization works
pipeline = FactPipeline([MyTransform(field="email")])
spec = pipeline.to_dict()  # Serialize to dict
restored = FactPipeline.from_dict(spec)  # Deserialize from dict
```

---

## How FactPipeline Works (Under the Hood)

When you create a pipeline, FactPipeline checks each item:

```python skip
normalize = FactPipeline(
    [
        Flatten(),  # Is this a Transform? ✓ Yes → Use it
        MyTransform(field="email"),  # Is this a Transform? ✓ Yes → Use it
        "invalid",  # Is this a Transform? ✗ No → Error!
        plain_function,  # Is this a Transform? ✗ No → Error!
    ]
)
```

The check is: `isinstance(thing, Transform)`

That's why:
- ✅ All `Transform` subclasses work (built-in or custom)
- ❌ Plain functions fail
- ❌ Plain classes fail (unless they inherit from `Transform`)
- ❌ Strings fail
- ❌ Generic callables fail

---

## Common Pitfalls & Solutions

### Pitfall 1: Forgetting the `metadata` Property

```python skip
# ❌ Wrong: AttributeError on execution
class MyTransform(Transform):
    def __call__(self, fact):
        return fact

    # Missing: @property metadata


# ✅ Right: Always provide metadata
class MyTransform(Transform):
    def __call__(self, fact):
        return fact

    @property
    def metadata(self):
        return TransformMetadata(name="MyTransform")
```

### Pitfall 2: Mutating the Input Fact

```python
# ❌ Wrong: Causes hard-to-debug issues with retries/error policies
class BadTransform(Transform):
    def __call__(self, fact):
        fact["new_field"] = "value"  # MUTATES INPUT!
        return fact


# ✅ Right: Always create a copy
class GoodTransform(Transform):
    def __call__(self, fact):
        out = dict(fact)  # Create copy FIRST
        out["new_field"] = "value"
        return out
```

### Pitfall 3: Not Handling Missing Fields

```python
# ❌ Wrong: Crashes if field is missing
class BadTransform(Transform):
    def __call__(self, fact):
        return {**fact, "upper": fact["name"].upper()}  # KeyError if no "name"


# ✅ Right: Check for field existence
class GoodTransform(Transform):
    def __call__(self, fact):
        if "name" not in fact:
            return fact  # Or raise ValueError to trigger error policy
        out = dict(fact)
        out["upper"] = fact["name"].upper()
        return out
```

### Pitfall 4: Over-wrapping Transforms in FactPipeline

Transforms compose directly with `>>` and `|` - no need to wrap each one in
its own `FactPipeline` first.

```python skip
my_transform = MyClass()  # inherits from Transform
another = AnotherClass()  # inherits from Transform

# ✅ Right: Chain transforms directly
pipeline = my_transform >> another

# ✅ Also fine: pass them as a list
pipeline = FactPipeline([my_transform, another])

# 😕 Unnecessary: works, but verbose
pipeline = FactPipeline([my_transform]) >> FactPipeline([another])
```

`>>` only works when both sides inherit from `Transform` (or are
`FactPipeline`s). A plain function or bare class doesn't define `>>` and will
raise `TypeError` - the fix is to make it a `Transform` subclass, not to wrap
it in a `FactPipeline`.


---

## When to Create a Custom Transform

| Scenario | Do This |
|----------|---------|
| Apply a simple function to a field | Use `MapValues(fn, fields=[...])` |
| Validate data | Create a `Transform` that raises `ValueError` |
| Enrich from external data | Create a stateful `Transform` with a database connection |
| Complex multi-step logic | Compose multiple transforms with `>>` and `Conditional` |
| Serialize to YAML | Implement `to_dict()` and `from_dict()` |

---

## Complete Working Example

Here's a complete, production-ready example combining everything:

```python
from fluxrules.pipeline import (
    FactPipeline,
    Flatten,
    Require,
    Transform,
    TransformMetadata,
    ErrorPolicy,
    ErrorAction,
    FactLoader,
    IterableSource,
)
from typing import Any


# Your custom transforms
class ValidateEmail(Transform):
    def __call__(self, fact):
        email = fact.get("email", "")
        if "@" not in email:
            raise ValueError(f"Invalid email: {email}")
        return fact

    @property
    def metadata(self):
        return TransformMetadata(
            name="ValidateEmail",
            required_input_fields=["email"],
            errors_raised=[ValueError],
        )


class Uppercase(Transform):
    def __init__(self, fields):
        self.fields = fields

    def __call__(self, fact):
        out = dict(fact)
        for field in self.fields:
            if isinstance(out.get(field), str):
                out[field] = out[field].upper()
        return out

    @property
    def metadata(self):
        return TransformMetadata(
            name="Uppercase",
            required_input_fields=self.fields,
            output_fields=self.fields,
        )


# Create pipeline with custom transforms
pipeline = FactPipeline(
    [
        Flatten(),
        Uppercase(fields=["country"]),
        ValidateEmail(),
        Require(["email", "user_id"]),
    ],
    name="normalize",
    error_policy=ErrorPolicy(
        default=ErrorAction.FAIL,
        routes={ValueError: ErrorAction.SKIP},
    ),
)

# Process data
facts = [
    {"user": {"id": "u1"}, "email": "alice@example.com", "country": "us"},
    {"user": {"id": "u2"}, "email": "invalid", "country": "uk"},  # Invalid → skip
    {"user": {"id": "u3"}, "email": "bob@example.com", "country": "ng"},
]

loader = FactLoader(IterableSource(facts), pipeline, on_error="collect")

print("Processed facts:")
for fact in loader:
    print(f"  {fact}")

print(f"\nSkipped: {len(loader.dead_letter)} records")
for dead in loader.dead_letter:
    print(f"  {dead['error']}: {dead['data']}")
```

---

## Resources

| Resource | Purpose |
|----------|---------|
| **[Custom Transforms Guide](custom-transforms.md)** | Comprehensive patterns and best practices |
| **[Custom Transforms Cheat Sheet](custom-transforms-cheatsheet.md)** | Quick reference and decision tree |
| **[Example 29: Custom Transforms](https://github.com/fluxrules/fluxrules/blob/main/examples/29_custom_transforms.py)** | 8 real-world working examples |
| **[FactPipeline Framework](fact-pipeline.md)** | Full framework overview |
| **[Troubleshooting](troubleshooting.md)** | Common issues and solutions |

---

## TL;DR

✅ **You CAN create your own transforms**
- Inherit from `Transform`
- Implement `__call__` and `metadata`
- Use them in FactPipeline just like built-in transforms

❌ **You CANNOT use plain functions or generic classes**
- FactPipeline requires `isinstance(thing, Transform)` to be `True`
- Anything else will raise `AttributeError: 'object' has no attribute 'metadata'`

🎯 **Best practices**
- Always copy facts before modifying: `out = dict(fact)`
- Always implement `metadata` property
- Raise `ValueError` for validation errors, `KeyError` for transient failures
- Test transforms in isolation with pytest
