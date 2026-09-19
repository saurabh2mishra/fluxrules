# Conditions & Operators

This page documents all condition operators supported by FluxRules.

**Source:** `src/fluxrules/domain/dsl/` (DSL validation and execution)

---

## What is a Condition?

A condition is a test on a single fact field. It evaluates to true or false.

**Format:**
```python
{
    "type": "condition",
    "field": "amount",  # Field name in the fact
    "op": ">",  # Operator
    "value": 5000,  # Comparison value
}
```

**Use conditions to build rules:**
```python
from fluxrules.domain import Rule

rule = Rule(
    name="high_value",
    condition_dsl={
        "type": "condition",
        "field": "amount",
        "op": ">",
        "value": 5000,
    },
    action="manual_review",
)
```

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

# Rule 1: High amount
rule1 = Rule(
    name="high_amount",
    condition_dsl={"type": "condition", "field": "amount", "op": ">", "value": 2000},
    action="manual_review",
)

# Rule 2: High-risk country
rule2 = Rule(
    name="high_risk_country",
    condition_dsl={"type": "condition", "field": "country", "op": "in", "value": ["NG", "SN"]},
    action="block_payment",
)

# Rule 3: New account
rule3 = Rule(
    name="new_account",
    condition_dsl={"type": "condition", "field": "account_age_days", "op": "<", "value": 7},
    action="step_up_auth",
)

engine = PhreakEngine()
engine.load_rules([rule1, rule2, rule3])

fact = {"amount": 3000, "country": "NG", "account_age_days": 5}
result = engine.evaluate(fact)
print(f"Matched: {result.fired_rules}")  # [rule1, rule2, rule3]
```

---

## Combining Conditions (AND/OR/NOT)

Simple conditions can be combined using logical operators.

**See:** [Complex Conditions](complex-conditions.md) for AND/OR/NOT logic

---

## Example: Payment Risk Triage

All examples use operators in real payment-risk scenarios:

- **[01_conditions.py](https://github.com/fluxrules/fluxrules/blob/main/examples/01_conditions.py)** — Operator variety demo
- **[02_complex_conditions.py](https://github.com/fluxrules/fluxrules/blob/main/examples/02_complex_conditions.py)** — Nested operators
- **[13_complex_rules.py](https://github.com/fluxrules/fluxrules/blob/main/examples/13_complex_rules.py)** — Complex payment rules

**Run an example:**
```bash
cd examples
python 01_conditions.py
```

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

## Next Steps

- **[Complex Conditions](complex-conditions.md)** — Combine with AND/OR/NOT
- **[Validation Framework](validation-framework.md)** — Validate DSL structures
- **[Concepts](concepts.md)** — Understanding rules, engines, facts

    )
]

engine.load_rules(rules)
```

## Practical Examples

### Example 1: Customer Eligibility

Check if a customer is eligible for a premium membership:

```python
from fluxrules.domain import Rule
from fluxrules.engine.phreak import PhreakEngine

engine = PhreakEngine()

rule = Rule(
    name="Premium Member Eligible",
    condition_dsl={
        "type": "and",
        "children": [
            {"type": "condition", "field": "account_age_months", "op": ">=", "value": 12},
            {"type": "condition", "field": "total_purchases", "op": ">", "value": 5000}
        ]
    },
    action="qualify_for_premium"
)

engine.load_rules([rule])

# Test it
customer = {"account_age_months": 24, "total_purchases": 8000}
result = engine.evaluate(customer)
print(f"Matched: {result.fired_rules}")  # [1] if matched
```

### Example 2: Order Fulfillment

Determine shipping eligibility:

```python
rule = Rule(
    name="Express Shipping",
    condition_dsl={
        "type": "and",
        "children": [
            {"type": "condition", "field": "order_total", "op": ">=", "value": 100},
            {"type": "condition", "field": "shipping_country", "op": "in", "value": ["US", "CA"]},
        ],
    },
    action="enable_express_shipping",
)

engine.load_rules([rule])

order = {"order_total": 150, "shipping_country": "US"}
result = engine.evaluate(order)
print(f"Actions: {result.actions}")  # ['enable_express_shipping']
```

### Example 3: Risk Assessment

Evaluate transaction risk:

```python
rule = Rule(
    name="Flag High-Risk Transaction",
    condition_dsl={
        "type": "and",
        "children": [
            {"type": "condition", "field": "amount", "op": ">", "value": 10000},
            {"type": "condition", "field": "country", "op": "not_in", "value": ["US", "CA", "UK"]},
            {"type": "condition", "field": "account_age_days", "op": "<", "value": 30},
        ],
    },
    action="flag_high_risk",
)

engine.load_rules([rule])

transaction = {"amount": 12000, "country": "NZ", "account_age_days": 15}
result = engine.evaluate(transaction)
print(f"Risk flagged: {len(result.fired_rules) > 0}")
```

## Type Handling

Conditions automatically handle type comparisons:

### Strings
```python
# String equality
{"type": "condition", "field": "status", "op": "==", "value": "active"}

# String comparison (lexicographic)
{"type": "condition", "field": "last_name", "op": ">", "value": "Smith"}
```

### Numbers
```python
# Integer comparison
{"attribute": "age", "operator": ">=", "value": 18}

# Float comparison
{"attribute": "score", "operator": ">", "value": 0.85}
```

### Booleans
```python
# Boolean equality
{"attribute": "is_verified", "operator": "==", "value": True}
```

### Lists and Collections
```python
# Check membership
{"attribute": "roles", "operator": "contains", "value": "admin"}

# Check if in predefined set
{"attribute": "country_code", "operator": "in", "value": ["US", "CA", "MX"]}
```

### Null/None Handling
```python
# Check if field is null
{"attribute": "phone_number", "operator": "==", "value": None}

# Check if field is not null
{"attribute": "phone_number", "operator": "!=", "value": None}
```

## Best Practices

### 1. Be Specific
Good conditions answer clear questions:
```python
# Good: Clear intent
{"attribute": "order_total", "operator": ">", "value": 100}

# Ambiguous: What does this mean?
{"attribute": "x", "operator": ">", "value": 100}
```

### 2. Use Meaningful Attribute Names
```python
# Good
{"attribute": "customer_age", "operator": ">=", "value": 18}

# Unclear
{"attribute": "c_a", "operator": ">=", "value": 18}
```

### 3. Validate Value Types Match Attribute Types
```python
# Good: Value matches expected type
{"attribute": "age", "operator": ">=", "value": 18}

# Problematic: Value type mismatch
{"attribute": "age", "operator": ">=", "value": "eighteen"}
```

### 4. Order Collections in `in` Operator
```python
# Good: Alphabetical or logical order
{"attribute": "country", "operator": "in", "value": ["CA", "MX", "US"]}

# Still works, but less clear
{"attribute": "country", "operator": "in", "value": ["US", "MX", "CA"]}
```

### 5. Use `!=` Sparingly
Instead of checking for "not equal", consider using positive conditions:

```python
# Rather than:
{"attribute": "status", "operator": "!=", "value": "canceled"}

# Prefer:
{"attribute": "status", "operator": "in", "value": ["active", "pending", "completed"]}
```

## Debugging Conditions

### Enable Debug Mode
```python
engine = PhreakEngine()
# Engine will log condition evaluations
```

### Manually Test Conditions
```python
from fluxrules import PhreakEngine, Rule

# Build a one-rule engine to test a condition in isolation.
rule = Rule(
    name="adult_check",
    condition_dsl={"type": "condition", "field": "age", "op": ">=", "value": 18},
    action="allow",
)

engine = PhreakEngine()
engine.load_rules([rule])

result = engine.evaluate({"age": 21})
print(f"Matched: {result.fired_rules}")
print(f"Actions: {result.actions}")
```

### Print Intermediate Results
```python
from fluxrules import PhreakEngine, Rule

engine = PhreakEngine()
engine.load_rules(
    [
        Rule(
            name="active_adult",
            condition_dsl={"type": "condition", "field": "age", "op": ">=", "value": 18},
            action="allow",
        )
    ]
)

result = engine.evaluate({"age": 21, "status": "active"})

print(f"Matched rule ids: {result.fired_rules}")
print(f"Actions: {result.actions}")
for rule_id, explanation in result.explanations.items():
    print(rule_id, explanation)
```

## Next Steps

- **[Complex Conditions](complex-conditions.md)** - Learn how to combine simple conditions with AND/OR logic
- **[Domains & Tags](domains-and-tags.md)** - Organize conditions by domain and purpose
- **[Working Memory](working-memory.md)** - Maintain state across rule evaluations
