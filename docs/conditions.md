# Conditions & Operators
FluxRules uses a `condition_dsl` to define a condition or a group of conditions. It is not just a flat dictionary; it behaves like a small decision tree.

**Source:** `src/fluxrules/domain/dsl/` (DSL validation and execution)

---

## `condition_dsl`

`condition_dsl` is a small tree with a contract enforced by the validation logic.

A leaf is a single check, and a grouped node combines children.

- **`type`**: node kind.

    - *`"condition"`* = one field test; a condition node needs type, field, op, and value.

     ```python
     {"type": "condition", "field": "amount", "op": ">", "value": 2000}
     ``` 

    - *`"group"`* = combine children. A `group` node needs type plus children (or conditions) and usually op/logic.


    ```python
    {
        "type": "group",
        "op": "AND",
        "children": [
            {"type": "condition", "field": "amount", "op": ">", "value": 2000},
            {"type": "condition", "field": "country", "op": "in", "value": ["NG", "SN"]},
        ],
    }
    ```
    

The validator also accepts `"and"`, `"or"`, `"not"`, `"exists"`, `"sequence"`, and `"accumulate"`.

- **`field`**: fact field name as a string. Required for `condition` and `exists`.
- **`op`**: comparison operator such as `>`, `==`, `in`, `contains`. Required for `condition`.
- **`value`**: literal or list compared against the field.
- **`children`**: list of child DSL nodes for a grouped condition.
- **`condition`**: child node used by `not`.
- **`conditions`**: alternate spelling accepted for `children` in some parser/engine paths.
- **`logic`**: optional alias for the group logic in some builders/parsers; typically `AND` or `OR`.

---

## Operators (13, plus 6 word aliases)

All operators work on fact fields. The field must exist in your fact for the condition to evaluate.

The six comparison operators also accept word-form aliases, which are normalized
to their symbols before evaluation: `eq` (`==`), `ne` (`!=`), `gt` (`>`),
`gte` (`>=`), `lt` (`<`), `lte` (`<=`).

### Comparison Operators

**`==` Equal**
```python
{"type": "condition", "field": "status", "op": "==", "value": "active"}
# Matches: status == "active"
```

**`!=` Not Equal**
```python
{"type": "condition", "field": "status", "op": "!=", "value": "inactive"}
# Matches: status != "inactive"
```

**`>` Greater Than**
```python
{"type": "condition", "field": "amount", "op": ">", "value": 5000}
# Matches: amount > 5000
```

**`>=` Greater Than or Equal**
```python
{"type": "condition", "field": "age", "op": ">=", "value": 18}
# Matches: age >= 18
```

**`<` Less Than**
```python
{"type": "condition", "field": "inventory", "op": "<", "value": 10}
# Matches: inventory < 10 (low stock)
```

**`<=` Less Than or Equal**
```python
{"type": "condition", "field": "discount", "op": "<=", "value": 0.5}
# Matches: discount <= 0.5
```

### Collection Membership

**`in` Value in Collection**
```python
{"type": "condition", "field": "country", "op": "in", "value": ["NG", "SN", "GH"]}
# Matches: country in ["NG", "SN", "GH"]
```

**`not_in` Value not in Collection**
```python
{"type": "condition", "field": "tier", "op": "not_in", "value": ["bronze"]}
# Matches: tier not in ["bronze"]
```

### String/Collection Containment

**`contains` Collection/String Contains Value**
```python
{"type": "condition", "field": "tags", "op": "contains", "value": "premium"}
# Matches: "premium" in tags (if tags is a list or string)
```

**`not_contains` Collection/String Does Not Contain Value**
```python
{"type": "condition", "field": "flags", "op": "not_contains", "value": "fraud"}
# Matches: "fraud" not in flags
```

### String Matching

These operators coerce both sides to strings before matching.

**`starts_with` String Starts With**
```python
{"type": "condition", "field": "email", "op": "starts_with", "value": "admin"}
# Matches: str(email).startswith("admin")
```

**`ends_with` String Ends With**
```python
{"type": "condition", "field": "email", "op": "ends_with", "value": "@corp.com"}
# Matches: str(email).endswith("@corp.com")
```

**`regex` Regular Expression Match**
```python
{"type": "condition", "field": "card", "op": "regex", "value": "^4[0-9]{12}"}
# Matches: re.match("^4[0-9]{12}", str(card)) succeeds (anchored at the start)
```

---

## Real-World Examples

### Payment Risk Detection

```python
from fluxrules.domain import Rule
from fluxrules.engine.phreak import PhreakEngine

rule1 = Rule(
    name="high_amount",
    condition_dsl={"type": "condition", "field": "amount", "op": ">", "value": 2000},
    action="manual_review",
)

rule2 = Rule(
    name="high_risk_country",
    condition_dsl={"type": "condition", "field": "country", "op": "in", "value": ["NG", "SN"]},
    action="block_payment",
)

rule3 = Rule(
    name="new_account",
    condition_dsl={"type": "condition", "field": "account_age_days", "op": "<", "value": 7},
    action="step_up_auth",
)

engine = PhreakEngine()
engine.load_rules([rule1, rule2, rule3])

fact = {"amount": 3000, "country": "NG", "account_age_days": 5}
result = engine.evaluate(fact)
print(f"Matched: {result.fired_rules}")
```

---

## Combining Conditions (AND/OR/NOT)

Simple conditions can be combined using logical operators.

**See:** [Complex Conditions](complex-conditions.md) for AND/OR/NOT logic.

---

## Operator Reference Table

| Operator | Meaning | Type | Example |
|----------|---------|------|---------|
| `==` | Equal | Equality | `{"op": "==", "value": "active"}` |
| `!=` | Not Equal | Equality | `{"op": "!=", "value": "inactive"}` |
| `>` | Greater Than | Comparison | `{"op": ">", "value": 5000}` |
| `>=` | Greater Than or Equal | Comparison | `{"op": ">=", "value": 18}` |
| `<` | Less Than | Comparison | `{"op": "<", "value": 10}` |
| `<=` | Less Than or Equal | Comparison | `{"op": "<=", "value": 0.5}` |
| `in` | Value in Collection | Membership | `{"op": "in", "value": ["A", "B"]}` |
| `not_in` | Value not in Collection | Membership | `{"op": "not_in", "value": ["X"]}` |
| `contains` | Collection Contains Value | Containment | `{"op": "contains", "value": "tag"}` |
| `not_contains` | Collection Does Not Contain | Containment | `{"op": "not_contains", "value": "flag"}` |
| `starts_with` | String Starts With | String | `{"op": "starts_with", "value": "admin"}` |
| `ends_with` | String Ends With | String | `{"op": "ends_with", "value": "@corp.com"}` |
| `regex` | Regex Match (anchored at start) | String | `{"op": "regex", "value": "^4[0-9]{12}"}` |

---

## Best Practices

### 1. Keep the condition tree readable

Prefer a simple leaf condition when the rule is one test. Use a group only when you need to combine multiple tests.

### 2. Use the correct shape for grouped logic

```python
{
    "type": "group",
    "op": "AND",
    "children": [
        {"type": "condition", "field": "amount", "op": ">=", "value": 100},
        {"type": "condition", "field": "status", "op": "==", "value": "active"},
    ],
}
```

### 3. Match the value type to the field type

A numeric field should compare with a number, a string field with a string, and a list field with a collection.

---

## Next Steps

- **[Complex Conditions](complex-conditions.md)** - Learn how to combine simple conditions with AND/OR/NOT logic
- **[Validation Framework](validation-framework.md)** - Validate DSL structures
- **[Concepts](concepts.md)** - Understand rules, engines, and facts
