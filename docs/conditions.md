# Conditions & Rule Authoring

A rule's `conditions` field defines when the rule fires. FluxRules gives you
three ways to author conditions, the same condition tree on the wire for all
three, and a set of tools to validate before you deploy.

Start with [Authoring Rules](authoring-rules.md) for how to choose between them.
This page is the reference: every operator and every validation tool.

---

## Three ways to write conditions

### 1. F DSL - recommended for Python code

Write conditions as natural Python expressions using the `F` helper. Each
expression compiles to a condition dict the engine accepts; you never touch
raw dicts.

```python
from fluxrules import F, Rule

# Single leaf
rule = Rule(
    name="high_value",
    conditions=F("amount") > 5000,
    action="review",
)

# AND - both must hold
rule = Rule(
    name="high_value_us",
    conditions=(F("amount") > 5000) & (F("country") == "US"),
    action="review",
)

# OR - either suffices
rule = Rule(
    name="risky_origin",
    conditions=(F("country").isin(["NG", "SN"])) | (F("ip_risk_score") >= 70),
    action="block",
)

# NOT
rule = Rule(
    name="unverified",
    conditions=~F("verified").exists(),
    action="step_up",
)

# Composed
rule = Rule(
    name="fraud_triage",
    conditions=(
        (F("amount") > 2000)
        & (F("payment_method").isin(["crypto", "prepaid_card"]))
        & (
            (F("country").isin(["NG", "SN", "GH"]))
            | (F("ip_risk_score") >= 70)
        )
        & ~(F("email_domain").ends_with("trusted.example"))
    ),
    action="manual_review",
)
```

**Operator precedence warning** - Python's `&` and `|` bind more tightly than
comparisons like `>`, `<`, `==`. Always wrap each individual condition in
parentheses:

```python
# python skip - the second line deliberately raises to show the trap
# Correct
(F("amount") > 5000) & (F("country") == "US")

# Wrong - & binds before ==, raising a TypeError at runtime
F("amount") > 5000 & F("country") == "US"
```

### 2. Dict / YAML - for config-driven rules

The dict format is the wire and storage format. Use it when rules come from a
database, YAML file, or API response.

```python
Rule(
    name="high_value",
    conditions={"type": "condition", "field": "amount", "op": ">", "value": 5000},
    action="review",
)
```

YAML (loaded with `load_rules_from_yaml`, see [YAML Rules](yaml-rules.md)):

```yaml
name: high_value
conditions:
  type: condition
  field: amount
  op: ">"
  value: 5000
action: review
```

AND/OR in dict form:

```python
{
    "type": "group",
    "op": "AND",
    "children": [
        {"type": "condition", "field": "amount", "op": ">", "value": 5000},
        {"type": "condition", "field": "country", "op": "==", "value": "US"},
    ],
}
```

The F DSL and the dict format describe the same conditions. Mix them freely: a
`Rule` built with `F(...)` stores a dictionary tree like one built from a dict,
and loads back from YAML the same way. One difference in shape: `a & b & c`
nests as `(a & b) & c`, where a hand-written dict usually has one flat group of
three. Both give the same results.

### 3. RuleBuilder - fluent step-by-step construction

`RuleBuilder` chains method calls and validates each step. Useful when building
rules programmatically where you want to catch errors early.

```python
from fluxrules import F, RuleBuilder

rule = (
    RuleBuilder()
    .name("high_value_us")
    .priority(10)
    .condition((F("amount") > 5000) & (F("country") == "US"))
    .action("review")
    .build()
)
```

`.condition()` accepts both an `F` expression and a raw dict.

---

## All available operators

### Comparison (Python dunders)

| F expression | Dict `"op"` | Meaning |
|---|---|---|
| `F("x") == v` | `"=="` or `"eq"` | Equal |
| `F("x") != v` | `"!="` or `"ne"` | Not equal |
| `F("x") > v` | `">"` or `"gt"` | Greater than |
| `F("x") >= v` | `">="` or `"gte"` | Greater than or equal |
| `F("x") < v` | `"<"` or `"lt"` | Less than |
| `F("x") <= v` | `"<="` or `"lte"` | Less than or equal |

The six comparison operators also accept their word-form aliases in dict/YAML
(`eq`, `ne`, `gt`, `gte`, `lt`, `lte`), normalised before evaluation.

### Collection membership

| F expression | Dict `"op"` | Meaning |
|---|---|---|
| `F("x").isin(["a", "b"])` | `"in"` | Value is a member of the list |
| `F("x").not_in(["a"])` | `"not_in"` | Value is not a member |

### String / collection containment

| F expression | Dict `"op"` | Meaning |
|---|---|---|
| `F("x").contains("tag")` | `"contains"` | Collection or string contains value |
| `F("x").not_contains("flag")` | `"not_contains"` | Does not contain |

### String matching

Both sides are coerced to strings before matching.

| F expression | Dict `"op"` | Meaning |
|---|---|---|
| `F("x").starts_with("adm")` | `"starts_with"` | `str(x).startswith(...)` |
| `F("x").ends_with(".com")` | `"ends_with"` | `str(x).endswith(...)` |
| `F("x").regex("^4[0-9]{12}")` | `"regex"` | `re.search(pattern, str(x))` - matches anywhere in the string, so add `^` to anchor at the start |

### Boolean composition (F DSL)

| Operator | Meaning | Dict equivalent |
|---|---|---|
| `a & b` | AND | `{"type": "group", "op": "AND", "children": [a, b]}` |
| `a \| b` | OR | `{"type": "group", "op": "OR", "children": [a, b]}` |
| `~a` | NOT | `{"type": "not", "condition": a}` |

### Field presence

```python
F("email").exists()          # True when "email" key is in facts and not None
~F("email").exists()         # True when "email" is absent or None
```

Dict equivalent:

```python
{"type": "exists", "field": "email"}
```

Use `exists()` when a field might legitimately be absent - `condition` nodes
raise `FieldNotFoundError` if the field is a case variant of a present key
(e.g. `Amount` vs `amount`). `exists()` never raises.

---

## What to keep in mind when authoring rules

### Field names are exact and case-sensitive

`F("Amount")` and `F("amount")` are different fields. If a fact arrives with
`{"amount": 5000}` and the condition says `F("Amount")`, the rule raises a
`FieldNotFoundError` because the field is a case variant of a present key.
For genuinely different schemas (multi-domain rulesets), absent fields that are
not a case variant of any present key return `False` silently, which is the
correct behaviour.

```python
# Fact: {"amount": 5000}
F("Amount") > 1000   # raises FieldNotFoundError - did you mean 'amount'?
F("amount") > 1000   # evaluates correctly
```

### Operator precedence: always use parentheses

Python evaluates `&` and `|` before `>`, `<`, `==`. The rule is simple: wrap
every individual `F(...)` comparison in its own parentheses before composing:

```python
# python skip - the unsafe line deliberately raises to show the trap
# safe - each leaf is wrapped
(F("amount") > 5000) & (F("country") == "US")

# unsafe - raises TypeError
F("amount") > 5000 & F("country") == "US"
```

### Use `exists()` for optional fields

A `condition` node on a field that is absent raises (if the name looks like a
typo) or returns `False` (if genuinely different schema). When a field is
intentionally optional, guard it with `exists()`:

```python
# Only fires if "promo_code" is present AND matches
F("promo_code").exists() & (F("promo_code") == "SUMMER24")
```

### Value types must match

A numeric field compared with a string will not raise, but will silently not
match. Match the value type to the field type:

```python
F("amount") > 5000      # number field → number value
F("status") == "active" # string field → string value
F("tags").contains("vip")  # list field → scalar value to find in it
```

### `isin` takes a list, not positional args

```python
# python skip - the second line deliberately raises to show the trap
F("country").isin(["NG", "SN", "GH"])   # correct
F("country").isin("NG", "SN", "GH")    # wrong - TypeError
```

### Combining AND chains cleanly

For long AND chains, align the `&` operators at the start of each line:

```python
conditions=(
    (F("amount") > 2000)
    & (F("payment_method").isin(["crypto", "prepaid_card"]))
    & (F("chargeback_ratio") >= 0.1)
    & ~(F("email_domain").ends_with("trusted.example"))
),
```

---

## Validation

FluxRules validates condition trees at rule construction time (Pydantic) and
exposes an explicit validate step for bulk checks before deployment.

### Automatic validation at construction

Invalid conditions are caught when you build the `Rule`:

```python
# python skip - this block deliberately raises to show the validation error
from fluxrules import F, Rule

Rule(
    name="bad",
    conditions={"type": "condition", "field": "x", "op": "???", "value": 1},
    action="flag",
)
# raises ConditionValidationError: unknown operator '???'
```

Missing required keys, unknown operators, and malformed tree shapes all raise
`ConditionValidationError` immediately.

### `validate()` - check a batch without evaluating

```python
from fluxrules import F, Rule, validate

rules = [
    Rule(name="r1", conditions=F("amount") > 5000, action="flag"),
    Rule(name="r2", conditions=F("status") == "active", action="allow"),
]

issues = validate(rules)
if issues:
    for issue in issues:
        print(issue)
else:
    print("All rules valid")
```

`validate()` returns a list of human-readable strings - empty means all rules
passed. Use it in CI before deploying a new ruleset.

### `FieldNotFoundError` at evaluation time

When a `condition` field is absent from the incoming fact and the name is a
case variant of a present key (e.g. `Amount` vs `amount`), the engine raises
instead of silently returning False:

```python
from fluxrules import F, FieldNotFoundError, Rule, evaluate

rule = Rule(name="r", conditions=F("Amount") > 5000, action="flag")
try:
    evaluate(rule, {"amount": 6000})
except FieldNotFoundError as e:
    print(e)
# Field 'Amount' not found in fact. Did you mean 'amount'? Available keys: ['amount']
```

To deliberately test whether a field is present before comparing its value, use
`F("field").exists()`:

```python
# Does not raise even when "score" is absent
F("score").exists() & (F("score") >= 90)
```

### Full validation example

```python
from fluxrules import F, Rule, validate

rules = [
    Rule(
        name="fraud_check",
        conditions=(
            (F("amount") > 10000)
            & (F("country").isin(["NG", "SN", "GH"]))
            & ~(F("verified").exists())
        ),
        action="block",
        priority=10,
    ),
    Rule(
        name="vip_fast_track",
        conditions=(F("tier") == "gold") | (F("spend_ytd") >= 50000),
        action="expedite",
        priority=5,
    ),
]

issues = validate(rules)
assert issues == [], issues

from fluxrules import evaluate

fact = {"amount": 15000, "country": "NG"}
result = evaluate(rules, fact)
print(result.fired_rules)   # rule ids that matched
print(result.actions)       # ["block"]
```

---

## Condition tree reference

The dict / YAML format uses these node shapes:

| Node type | Required keys | Optional keys |
|---|---|---|
| `condition` | `type`, `field`, `op`, `value` | - |
| `group` / `and` / `or` | `type`, `children` (or `conditions`) | `op` (default `AND`) |
| `not` | `type`, `condition` | - |
| `exists` | `type`, `field` | - |

Accepted aliases: `"and"`, `"or"`, `"not"`, `"exists"`, `"group"`, `"composite"`.

---

## Next steps

- **[Complex Conditions](complex-conditions.md)** - AND/OR/NOT deep-dive with
  more examples
- **[Validation Framework](validation-framework.md)** - CI integration and
  custom validators
- **[YAML Rules](yaml-rules.md)** - rules as configuration files
- **[Rule Builder](rule-builder.md)** - `RuleBuilder` fluent API reference
