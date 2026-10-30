# Authoring Rules

A rule is a condition plus an action. The condition says when the rule fires.
This page explains the ways to write that condition, which one to pick first, and
why.

**Short answer:** write conditions with `F` expressions. Use a dictionary or YAML
only when your rules come from outside your Python code.

---

## The same rule, four ways

All four forms below describe one rule: "fire when the amount is over 5000 and the
country is US."

```python
from fluxrules import F, Rule, RuleBuilder

# 1. F expression (first choice)
by_expression = Rule(
    id=1,
    name="high_value_us",
    conditions=(F("amount") > 5000) & (F("country") == "US"),
    action="review",
)

# 2. RuleBuilder, step by step (it also takes an F expression)
by_builder = (
    RuleBuilder(1)
    .name("high_value_us")
    .condition((F("amount") > 5000) & (F("country") == "US"))
    .action("review")
    .build()
)

# 3. Dictionary (the stored format)
by_dict = Rule(
    id=1,
    name="high_value_us",
    conditions={
        "type": "group",
        "op": "AND",
        "children": [
            {"type": "condition", "field": "amount", "op": ">", "value": 5000},
            {"type": "condition", "field": "country", "op": "==", "value": "US"},
        ],
    },
    action="review",
)

# They are the same rule underneath.
assert by_expression.conditions == by_builder.conditions == by_dict.conditions
```

The fourth form is a YAML file, which holds the same dictionary:

```yaml
- id: 1
  name: high_value_us
  action: review
  conditions:
    type: group
    op: AND
    children:
      - {type: condition, field: amount, op: ">", value: 5000}
      - {type: condition, field: country, op: "==", value: US}
```

---

## Which one should I use?

| You are... | Use | Why |
|---|---|---|
| Writing rules in Python code | **`F` expressions** | Shortest, reads like the rule, checked by your editor |
| Building a rule step by step in code | `RuleBuilder` | Fields are set one at a time and checked as you go |
| Loading rules from a database or an API | Dictionary | That is the format they are stored in |
| Letting people edit rules without touching code | YAML | A plain file, no Python needed |

If you are unsure, start with `F`. You can always print the dictionary behind an
expression with `.to_dict()`, so nothing is hidden.

---

## Why `F` comes first

**It reads like the rule.** Compare the two:

```python
(F("amount") > 5000) & (F("country") == "US")
```

```python
{"type": "group", "op": "AND", "children": [
    {"type": "condition", "field": "amount", "op": ">", "value": 5000},
    {"type": "condition", "field": "country", "op": "==", "value": "US"}]}
```

Same meaning. The first is one line and the second is four. The shared example rule
in `examples/` has eight checks and two nested ORs. It is about 10 lines with `F`
and about 70 as a dictionary, and the dictionary buries the logic in brackets.

**It catches mistakes early.** An editor can see that `F("amount") > 5000` is
Python. It cannot see that `"op": ">"` is an operator, so a typo such as
`"op": "=>"` only shows up when the rule is built.

**It costs nothing at run time.** `F` is a thin layer over the dictionary. An
expression turns into the same dictionary the engine always used, so stored
rules, YAML files and the HTTP API do not change. There is no second engine and
no slower path.

### How it works

`F("amount")` is a field reference. Python's comparison operators on it do not
return `True` or `False`. They return a `Condition` object that holds a
dictionary:

| You write | It builds |
|---|---|
| `F("x") > 5` | `{"type": "condition", "field": "x", "op": ">", "value": 5}` |
| `a & b` | `{"type": "group", "op": "AND", "children": [a, b]}` |
| `a \| b` | `{"type": "group", "op": "OR", "children": [a, b]}` |
| `~a` | `{"type": "not", "condition": a}` |
| `F("x").exists()` | `{"type": "exists", "field": "x"}` |

`Rule(conditions=...)` and `RuleBuilder.condition(...)` accept a `Condition` or a
dictionary, and a `Condition` is turned into its dictionary right away. After
that point there is only one format.

One detail: `a & b & c` builds nested groups, `(a & b) & c`, while a dictionary
you write by hand usually has one flat group of three. They give the same
results. Only the shape differs.

---

## What to keep in mind

**Wrap every comparison in parentheses.** Python applies `&` and `|` before `>`
and `==`, so without parentheses the expression means something else and usually
fails with a `TypeError`.

```python
# python skip: the second line deliberately raises to show the trap
(F("amount") > 5000) & (F("country") == "US")   # correct
F("amount") > 5000 & F("country") == "US"       # wrong
```

**Field names are exact.** `F("Amount")` and `F("amount")` are different fields,
and so are `F("userAge")` and `F("user_age")`. If a fact has `user_age` and a
rule asks for `userAge` (or `Amount` against `amount`), FluxRules raises
`FieldNotFoundError` and suggests the right name, instead of quietly never
matching. A field that is simply not in the fact, with no look-alike key,
returns `False`. That keeps rulesets that serve different kinds of facts working.

**Write rules against a model when you have one.** `fields(Customer).age >= 18`
builds the same condition as `F("age") >= 18`, but a misspelt field fails when
you write the rule. See [Typed Facts](typed-facts.md).

**Mind `NOT` over optional fields.** `~(F("blocked") == True)` also fires when
`blocked` is missing. Say what you mean with `exists()`, and see
[Missing fields and NOT](conditions.md#missing-fields-and-not).

**Use `exists()` for fields that may be missing.** `F("promo").exists()` is true
when the key is present and not `None`, and it never raises.

**Pass a list to `isin`.** Write `F("country").isin(["NG", "GH"])`, not
`F("country").isin("NG", "GH")`.

**Match the type of the value to the type of the field.** Comparing a number
field to a string does not raise. It just never matches.

---

## Check a rule before you use it

There are four layers, from earliest to latest:

1. **When you build the `Rule`.** An unknown operator, a missing key or a
   malformed tree raises `ConditionValidationError` immediately. Field
   references from `fields(Model)` also fail here if the model lacks the field.
2. **Before you deploy.** `validate(rules)` checks a whole list and returns a list
   of problems, empty when all is well. Run it in CI.
3. **When rules load.** An engine built with `fact_schema=Model` raises
   `UnknownFieldError` for any rule field the model lacks, and loads nothing.
4. **While evaluating.** `FieldNotFoundError` flags a field name whose key is in
   the fact in another key style (`Amount` / `amount`, `userAge` / `user_age`).

```python
from fluxrules import F, Rule, validate

rules = [
    Rule(name="r1", conditions=F("amount") > 5000, action="flag"),
    Rule(name="r2", conditions=F("status") == "active", action="allow"),
]

assert validate(rules) == []
```

See [Conditions](conditions.md) for every operator and the full validation guide.

---

## Moving existing dictionary rules to `F`

You do not have to. Dictionaries keep working and can sit next to `F` rules in the
same ruleset. When you do want to switch, the mapping is mechanical:

| Dictionary | `F` expression |
|---|---|
| `{"type": "condition", "field": "x", "op": ">", "value": 5}` | `F("x") > 5` |
| `"op": "in", "value": [...]` | `F("x").isin([...])` |
| `"op": "contains"` | `F("x").contains(v)` |
| `{"type": "group", "op": "AND", "children": [a, b]}` | `a & b` |
| `{"type": "group", "op": "OR", "children": [a, b]}` | `a \| b` |
| `{"type": "not", "condition": a}` | `~a` |
| `{"type": "exists", "field": "x"}` | `F("x").exists()` |

---

## Next steps

- **[Conditions](conditions.md)**: every operator, with F and dictionary forms
- **[Complex Conditions](complex-conditions.md)**: AND, OR, NOT and nesting
- **[Rule Builder](rule-builder.md)**: the step-by-step API
- **[YAML Rules](yaml-rules.md)**: rules as files
- **[Rule Types](rule-types.md)**: `Rule` and the other rule models
