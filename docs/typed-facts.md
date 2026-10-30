# Typed Facts

**Prerequisites:** [Concepts](concepts.md) (Fact) and [Conditions](conditions.md).

---

Facts reach the engine as a flat `dict`. When your facts already have a shape,
for example a Pydantic model behind an API, you can hand that shape to
FluxRules and get three things in return:

1. **Pass models straight in.** `engine.evaluate(order)` works for Pydantic
   models, dataclasses, attrs classes and msgspec structs.
2. **Rules checked against the model.** With `fact_schema=Order`, `load_rules`
   refuses a rule that names a field `Order` does not have. This costs nothing
   per fact.
3. **Incoming keys normalized (opt-in).** With `validate_facts="normalize"`,
   each dict is validated by Pydantic, so `userAge`, `UserAge` and `user-age`
   all arrive as `user_age`, and `"42"` arrives as `42`.

Everything is opt-in. Engines without a `fact_schema` behave as before, and
plain dicts stay the fastest input.

!!! note "What a schema can and cannot promise"
    A schema guarantees that **rules agree with the model**: that is checked
    completely when rules load. It cannot guarantee that **incoming data agrees
    with the model**, because an upstream service can still rename a key or
    send `"abc"` for a number. What it does guarantee is that such a mismatch is
    never silent: it fails at `load_rules`, or at `evaluate` under the policy
    you choose with `on_invalid`.

## Pass a model to the engine

Nested models become dotted keys, the same shape the `Flatten` transform
produces. Keys are the Python field names, not aliases, because rules use field
names.

```python
from pydantic import BaseModel, ConfigDict

from fluxrules import F, Rule, to_fact_dict
from fluxrules.engine.phreak import PhreakEngine
from fluxrules.facts import lenient_aliases


class Customer(BaseModel):
    model_config = ConfigDict(alias_generator=lenient_aliases())

    user_age: int
    country: str = "US"
    blocked: bool | None = None


class Order(BaseModel):
    amount: float
    customer: Customer


order = Order(amount=250, customer=Customer(user_age=30))
assert to_fact_dict(order) == {
    "amount": 250.0,
    "customer.user_age": 30,
    "customer.country": "US",
    "customer.blocked": None,
}

engine = PhreakEngine()
engine.load_rules(
    [Rule(id=1, name="adult", conditions=F("customer.user_age") >= 18, action="allow")]
)
assert engine.evaluate(order).fired_rules == [1]
```

`fluxrules.evaluate(rules, facts)` accepts the same inputs.

## Check rules against a schema

Give the engine the model as `fact_schema`. Every field each rule references,
including `exists()` fields, is checked once when the rules load. A rule naming
an unknown field raises `UnknownFieldError` with a suggestion, and nothing from
that `load_rules` call is loaded:

```python
from fluxrules import UnknownFieldError

checked = PhreakEngine(fact_schema=Order)

try:
    checked.load_rules(
        [Rule(id=1, name="adult", conditions=F("customer.userAge") >= 18, action="allow")]
    )
except UnknownFieldError as exc:
    print(exc)
    # Rule 'adult' references unknown field 'customer.userAge' (not in fact
    # schema Order). Did you mean 'customer.user_age'? Known fields: [...]

checked.load_rules(
    [Rule(id=1, name="adult", conditions=F("customer.user_age") >= 18, action="allow")]
)
```

`fact_schema` accepts a Pydantic model, dataclass, attrs class, msgspec
`Struct` or `TypedDict`. One engine checks against one schema, so keep rules
for different fact shapes in different engines.

## Write rules with checked field references

`fields(Model)` catches the typo even earlier, at the line that writes the
rule. Each attribute is an ordinary `F` reference, so every operator works:

```python
from fluxrules.facts import fields

o = fields(Order)
rule = Rule(
    id=2,
    name="big_us_order",
    conditions=(o.amount > 100) & (o.customer.country == "US"),
    action="review",
)
assert rule.conditions["children"][0]["field"] == "amount"

try:
    o.customer.contry  # noqa: B018
except UnknownFieldError as exc:
    assert "Did you mean 'customer.country'" in str(exc)

print(dir(o.customer))  # ['blocked', 'country', 'user_age'] - IDE-style discovery
```

Rules built this way serialize to the usual condition dict, so they store and
load exactly like `F` rules.

## Normalize incoming keys

`lenient_aliases()` is a Pydantic alias generator. For each field it accepts
the snake_case, camelCase, PascalCase, kebab-case and all-lowercase spellings
(`user_age`, `userAge`, `UserAge`, `user-age`, `userage`). The spellings are
listed per field, so a key that is not a spelling of a declared field is never
folded into one.

Turn on per-fact validation to apply it on every `evaluate`:

```python
normalizing = PhreakEngine(fact_schema=Customer, validate_facts="normalize")
normalizing.load_rules(
    [Rule(id=1, name="adult", conditions=F("user_age") >= 18, action="allow")]
)

for payload in ({"user_age": 30}, {"userAge": "30"}, {"UserAge": 30}, {"user-age": 30}):
    assert normalizing.evaluate(payload).fired_rules == [1]
```

| `validate_facts` | What happens to a dict fact | Cost |
|---|---|---|
| `"off"` (default) | Used as-is | none |
| `"normalize"` | Validated by Pydantic in lax mode: aliases rename keys, values are coerced (`"30"` → `30`), defaults fill in | about 2-4 µs per fact |
| `"strict"` | Validated in Pydantic strict mode: aliases still apply, no type coercion | about 2-4 µs per fact |

A model instance of `fact_schema` is already valid and skips validation. A
nested dict payload is validated against the nested model, then flattened.
Validation needs a schema Pydantic can validate: a Pydantic model, a dataclass
or a `TypedDict` (from `typing_extensions` on Python 3.11).

## How a fact reaches the engine

| Input to `evaluate()` | `validate_facts="off"` (default) | `validate_facts="normalize"` / `"strict"` |
|---|---|---|
| `dict` | Used as-is | Validated against `fact_schema`, then flattened |
| Instance of `fact_schema` | Converted with `to_fact_dict` | Already valid: converted, not re-validated |
| Any other model (Pydantic, dataclass, attrs, msgspec) | Converted with `to_fact_dict` | Converted, then validated against `fact_schema` |
| Other `Mapping` (e.g. `MappingProxyType`) | Copied to a `dict` | Validated against `fact_schema`, then flattened |

The same path serves `evaluate_by_domain`, `evaluate_by_tags`,
`evaluate_all`, `evaluate_with_actions` and streaming mode, since they all call
`evaluate()`. With `strict_facts=True`, the structural flat-fact check runs on
the converted (or validated) dict.

Two entry points do **not** validate:

- `engine.assert_fact(...)` converts a model but never validates it. Working
  memory is not read by `evaluate()`.
- `fluxrules.evaluate(rules, facts)` converts a model but has no `fact_schema`,
  so aliases are not applied. Use an engine with `fact_schema` when incoming
  keys need normalizing.

Indicative costs per fact, measured on CPython 3.11 with a five-field model
(order of magnitude, not a guarantee):

| Step | Cost |
|---|---|
| `dict` passed through | ~0.07 µs |
| Flat Pydantic model converted | ~0.9 µs (a `model_dump()` is ~0.7 µs) |
| Nested Pydantic model converted | ~1.9 µs |
| Dataclass converted | ~1.1 µs |
| `validate_facts` on a flat dict | ~2.3 µs |
| `validate_facts` on a nested dict | ~3.6 µs |
| `fact_schema` rule check | once per `load_rules`, nothing per fact |

## Decide what happens to invalid facts

`on_invalid` sets the policy when validation fails:

```python
from fluxrules import FactValidationError

strict = PhreakEngine(fact_schema=Customer, validate_facts="normalize")
strict.load_rules([Rule(id=1, name="adult", conditions=F("user_age") >= 18, action="allow")])

try:
    strict.evaluate({"userAge": "abc"})
except FactValidationError as exc:
    assert exc.errors[0]["type"] == "int_parsing"  # Pydantic error code and location

tolerant = PhreakEngine(fact_schema=Customer, validate_facts="normalize", on_invalid="quarantine")
tolerant.load_rules([Rule(id=1, name="adult", conditions=F("user_age") >= 18, action="allow")])

assert tolerant.evaluate({"userAge": "abc"}).fired_rules == []
[rejected] = tolerant.quarantined_facts
assert rejected.facts == {"userAge": "abc"}
```

| `on_invalid` | Result |
|---|---|
| `"raise"` (default) | `FactValidationError` with `.errors` (field location and error code for each problem) |
| `"skip"` | Empty result, and a warning is logged |
| `"quarantine"` | Empty result; the fact and its error are kept in `engine.quarantined_facts` (the most recent 1000) |

Whether unknown keys are allowed is the model's choice: Pydantic ignores them
by default and rejects them with `model_config = ConfigDict(extra="forbid")`.

## Without a schema

Even with no schema, the engine reports key-style mismatches. A rule on
`userAge` against a fact carrying `user_age` raises `FieldNotFoundError` naming
the key it found, instead of quietly not matching. See
[Field names are exact](conditions.md#field-names-are-exact).

## Next Steps

- [Conditions](conditions.md) - including [missing fields and NOT](conditions.md#missing-fields-and-not)
- [Nested Facts](nested-facts.md)
- [Fact Pipeline](fact-pipeline.md) - transforms and loaders for raw input
