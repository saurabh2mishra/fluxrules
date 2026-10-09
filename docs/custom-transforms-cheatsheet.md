# FactPipeline Custom Transforms Cheat Sheet

Quick reference for your question: **"What happens if a user wants to pass his own transformation function or class instead of `Flatten()`?"**

---

## TL;DR

| Scenario | What Happens | Solution |
|----------|----------------|----------|
| **Plain function** | ❌ `AttributeError: 'function' has no attribute 'metadata'` | Wrap in a `Transform` class |
| **Plain class** (no `Transform` base) | ❌ `AttributeError: object has no attribute 'metadata'` | Inherit from `Transform` |
| **Class inheriting from `Transform`** | ✅ Works! Used as-is in the pipeline | Just implement `__call__` and `metadata` |
| **Function inside a `Transform` class** | ✅ Works! Best practice for small transforms | Implement `__call__` that uses the function |

---

## Your Example: What Needs to Happen

```python
from fluxrules.pipeline import FactPipeline, Flatten, Rename, FieldType, Defaults, Require

# Your original code:
normalize = FactPipeline(
    [
        Flatten(),  # ✅ Built-in (inherits from Transform)
        Rename({"user_id": ["user.id", "userId"]}),  # ✅ Built-in (inherits from Transform)
        FieldType({"amount": float}),  # ✅ Built-in (inherits from Transform)
        Defaults({"country": "US"}),  # ✅ Built-in (inherits from Transform)
        Require(["user_id", "amount"]),  # ✅ Built-in (inherits from Transform)
    ],
    name="normalize",
)
```

### What If You Want a Custom Transform?

```python
# python skip
# ❌ THIS WON'T WORK - Plain function
def my_flatten(fact):
    return {k.replace("_", "."): v for k, v in fact.items()}


normalize = FactPipeline(
    [  # ❌ THIS WON'T WORK - Plain function
        my_flatten,  # ❌ AttributeError: 'function' has no attribute 'metadata'
    ]
)


# ❌ THIS WON'T WORK - Plain class
class MyFlatten:
    def __call__(self, fact):
        return {k.replace("_", "."): v for k, v in fact.items()}


normalize = FactPipeline(
    [  # ❌ THIS WON'T WORK - Plain class
        MyFlatten(),  # ❌ AttributeError: 'MyFlatten' object has no attribute 'metadata'
    ]
)

# ✅ THIS WORKS - Transform class
from fluxrules.pipeline import Transform, TransformMetadata


class MyFlatten(Transform):
    def __call__(self, fact):
        return {k.replace("_", "."): v for k, v in fact.items()}

    @property
    def metadata(self):
        return TransformMetadata(name="MyFlatten", description="Replace underscores with dots")


normalize = FactPipeline(
    [  # ✅ THIS WORKS - Transform class
        MyFlatten(),  # ✅ Works!
        Flatten(),
        Require(["user_id", "amount"]),
    ]
)
```

---

## Three Ways to Add Custom Logic

### Way 1: Custom Transform Class (Recommended)

```python
from fluxrules.pipeline import Transform, TransformMetadata


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


# Use it
pipeline = FactPipeline([Uppercase(fields=["name", "country"])])
```

**Pros:**
- Full IDE support and type checking
- Supports serialization (YAML/JSON)
- Publishable metadata for introspection
- Works with error policies and hooks
- Unit testable in isolation

**Cons:**
- More boilerplate than a plain function

### Way 2: Use MapValues for Simple Cases

If you just want to apply a function to certain fields:

```python
from fluxrules.pipeline import MapValues

# Instead of creating a custom class for simple cases:
pipeline = FactPipeline(
    [
        MapValues(str.upper, fields=["name", "country"]),
        MapValues(int, fields=["amount"]),
    ]
)
```

**Pros:**
- No custom class needed
- Built-in error handling
- Simple and declarative

**Cons:**
- Limited to field-level transformations

### Way 3: Composition with Conditional

For branching logic, use composition instead of conditionals inside transforms:

```python
from fluxrules.pipeline import Conditional


# DON'T: Put branching inside a transform
class BadApproach(Transform):
    def __call__(self, fact):
        if fact.get("source") == "legacy":
            ...  # handle legacy
        else:
            ...  # handle modern
        # ... complex nested logic ...


# DO: Use Conditional composition
legacy_transform = FactPipeline([Rename({"id": ["legacy_id"]})])
modern_transform = FactPipeline([Rename({"id": ["modern_id"]})])

pipeline = Conditional(
    predicate=lambda f: f.get("source") == "legacy",
    then_transform=legacy_transform,
    else_transform=modern_transform,
)
```

---

## How FactPipeline Validates Transforms

When you pass something to `FactPipeline([...])`, it checks:

```python
# python skip
# Illustrative sketch of FactPipeline's internal dispatch, not runnable code.
class FactPipeline:
    def _eval(self, node, fact):
        # First check: Is this a Transform?
        if isinstance(node, Transform):  # ← This is where it fails for functions/plain classes
            return self._run_transform(node, fact)

        if isinstance(node, CompositionNode):  # ← Or a composition operator result
            ...  # handle composition
```

So **FactPipeline only accepts things that `isinstance(..., Transform)` returns `True` for**.

---

## Common Mistakes & Fixes

### Mistake 1: Forgetting `metadata` property

```python
# python skip
# ❌ WRONG
class MyTransform(Transform):
    def __call__(self, fact):
        return fact

    # Missing @property metadata


# Run it
pipeline = FactPipeline([MyTransform()])
# AttributeError: 'MyTransform' object has no attribute 'metadata'


# ✅ CORRECT
class MyTransform(Transform):
    def __call__(self, fact):
        return fact

    @property
    def metadata(self):
        return TransformMetadata(name="MyTransform")


pipeline = FactPipeline([MyTransform()])  # Works!
```

### Mistake 2: Mutating the input fact

```python
# ❌ WRONG: Modifies the input
class BadTransform(Transform):
    def __call__(self, fact):
        fact["new_field"] = "value"  # ← Mutates input!
        return fact


# This causes issues with retries and error policies
# because the original fact is already modified


# ✅ CORRECT: Create a copy
class GoodTransform(Transform):
    def __call__(self, fact):
        out = dict(fact)  # ← Create a copy
        out["new_field"] = "value"
        return out
```

### Mistake 3: Over-wrapping transforms in `FactPipeline`

Transforms compose directly with `>>` and `|`. You do **not** need to wrap
each one in its own `FactPipeline` first.

```python
# python skip
transform_a = MyClass()
transform_b = MyClass()

# ✅ CORRECT: Chain transforms directly
pipeline = transform_a >> transform_b

# ✅ ALSO CORRECT: Pass them as a list
pipeline = FactPipeline([transform_a, transform_b])

# 😕 UNNECESSARY: Works, but verbose - no need to wrap each transform
pipeline = FactPipeline([transform_a]) >> FactPipeline([transform_b])
```

> **Note:** `transform_a` and `transform_b` must still inherit from
> `Transform`. Plain functions and bare classes don't define `>>`, so they
> raise `TypeError`. The operators are provided by the `Transform` base class.


---

## Error Messages & What They Mean

| Error | Cause | Fix |
|-------|-------|-----|
| `AttributeError: 'function' has no attribute 'metadata'` | Passing a plain function | Wrap in a `Transform` class |
| `AttributeError: object has no attribute 'metadata'` | Class doesn't inherit from `Transform` | Add `: Transform` to class definition |
| `TypeError: unsupported operand type(s) for >>` | Using `>>` on a plain function/class (not a `Transform`) | Make it a `Transform` subclass (operators come from the base class) |
| `NotImplementedError: Transform does not support from_dict` | Can't serialize your transform | Implement `to_dict()` and `from_dict()` |
| `ValueError: Pipeline must have at least one transform` | Passing empty list `[]` | Add at least one transform |

---

## Decision Tree

```
"I want to add custom logic to my pipeline..."

  ├─ "It's just a simple function to call on one field"
  │  └─→ Use MapValues(fn, fields=[...])
  │
  ├─ "I need branching/conditional logic"
  │  └─→ Use Conditional(...) with composition operators
  │
  ├─ "I need validation or error handling"
  │  └─→ Create a Transform that raises ValueError
  │
  ├─ "I need to serialize to YAML/JSON later"
  │  └─→ Create a Transform with to_dict/from_dict
  │
  └─ "I need something more complex"
     └─→ Create a Transform class with __call__ and metadata
```

---

## Real-World Example from Your Question

```python
from fluxrules.pipeline import (
    FactPipeline,
    Flatten,
    Rename,
    FieldType,
    Defaults,
    Require,
    Transform,
    TransformMetadata,
)

# Your original normalize pipeline
normalize = FactPipeline(
    [
        Flatten(),  # nested -> dot notation
        Rename({"user_id": ["user.id", "userId"]}),  # first alias wins
        FieldType({"amount": float}),  # type coercion
        Defaults({"country": "US"}),  # fill missing fields
        Require(["user_id", "amount"]),  # fail-fast validation
    ],
    name="normalize",
)

fact = normalize({"user": {"id": "u_1"}, "amount": "1500"})
# Output: {'user.id': 'u_1', 'user_id': 'u_1', 'amount': 1500.0, 'country': 'US'}


# Now add a custom transform to the pipeline
class LogTransform(Transform):
    """Log each fact being processed."""

    def __init__(self, prefix="Processing"):
        self.prefix = prefix

    def __call__(self, fact):
        print(f"{self.prefix}: {fact}")
        return fact  # Pass through unchanged

    @property
    def metadata(self):
        return TransformMetadata(
            name="LogTransform", description=f"Log facts with prefix: {self.prefix}"
        )


# Add it to your pipeline
enhanced_normalize = FactPipeline(
    [
        Flatten(),
        Rename({"user_id": ["user.id", "userId"]}),
        LogTransform(prefix="After rename"),  # ← Your custom transform
        FieldType({"amount": float}),
        LogTransform(prefix="After coercion"),  # ← Another custom transform
        Defaults({"country": "US"}),
        Require(["user_id", "amount"]),
    ],
    name="enhanced_normalize",
)

fact = enhanced_normalize({"user": {"id": "u_1"}, "amount": "1500"})
# Output:
# After rename: {'user.id': 'u_1', 'user_id': 'u_1', 'amount': '1500'}
# After coercion: {'user.id': 'u_1', 'user_id': 'u_1', 'amount': 1500.0, 'country': 'US'}
```

---

## Summary

**The key rule:** All transforms in FactPipeline must inherit from `Transform`.

- **Can't pass:** Plain functions, generic classes, bare callables
- **Must pass:** Classes that inherit from `Transform` and implement `__call__` + `metadata`

For detailed patterns and examples, see:
- **[Custom Transforms Guide](custom-transforms.md)** - Comprehensive patterns and best practices
- **[Example 29: Custom Transforms](https://github.com/saurabh2mishra/fluxrules/blob/main/examples/29_custom_transforms.py)** - Real-world working examples
- **[FactPipeline Documentation](fact-pipeline.md)** - Full framework overview
