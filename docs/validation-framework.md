# Validation Framework

Validation in FluxRules catches errors in condition logic before rules are deployed.

**Prerequisites:** Familiarity with [Conditions](conditions.md) and condition DSL structure (see [Complex Conditions](complex-conditions.md)).

---

## What Gets Validated

When you create or load rules, FluxRules validates the condition DSL:

- **Syntax**: Structure, types, required fields
- **Semantics**: Valid operators, valid values
- **Logic**: No impossible conditions (e.g., `age > 18 AND age < 18`)

The validation system catches errors early with clear error messages.

**Source:** `src/fluxrules/domain/dsl/validation.py`

---

## How to Validate

### Validate a Single Rule's DSL

```python
from fluxrules.domain.dsl.validation import validate_dsl, DSLValidationError
from fluxrules.domain import Rule

# Define a rule with condition DSL
rule = Rule(
    name="high_amount_check",
    condition_dsl={
        "type": "group",
        "op": "AND",
        "children": [
            {"type": "condition", "field": "amount", "op": ">", "value": 5000},
            {"type": "condition", "field": "country", "op": "in", "value": ["US", "CA"]}
        ]
    },
    action="review"
)

# Validate the DSL
try:
    validate_dsl(rule.condition_dsl)
    print("✅ Rule is valid")
except DSLValidationError as e:
    print(f"❌ Validation error: {e}")
```

### Common Validation Errors

**Invalid operator:**
```python
invalid_dsl = {
    "type": "condition",
    "field": "amount",
    "op": "__unknown__",  # ❌ Not in VALID_OPERATORS
    "value": 100
}
# Raises: DSLValidationError: '__unknown__' is not a valid operator
```

**Impossible logic:**
```python
impossible_dsl = {
    "type": "group",
    "op": "AND",
    "children": [
        {"type": "condition", "field": "age", "op": ">", "value": 18},
        {"type": "condition", "field": "age", "op": "<", "value": 18}  # ❌ Impossible
    ]
}
# Note: validate_dsl validates structure; dead-rule detection is on the roadmap
```

**Missing required fields:**
```python
invalid_condition = {
    "type": "condition",
    "field": "amount"
    # ❌ Missing 'op' and 'value'
}
# Raises: DSLValidationError: missing required 'op' key
```

---

## DSL Node Types and Validation Rules

### condition

Tests a single field against a value using an operator.

**Required fields:** `type`, `field`, `op`, `value`

**Valid operators:** `==`, `!=`, `>`, `>=`, `<`, `<=`, `in`, `not_in`, `contains`, `not_contains`

```python
{"type": "condition", "field": "amount", "op": ">=", "value": 1000}
```

### group

Combines multiple conditions with AND or OR logic.

**Required fields:** `type`, `op`, `children`

**Valid op values:** `"AND"`, `"OR"` (case-insensitive; both uppercase and lowercase work)

```python
{
    "type": "group",
    "op": "AND",
    "children": [
        {"type": "condition", "field": "amount", "op": ">", "value": 100},
        {"type": "condition", "field": "status", "op": "==", "value": "active"}
    ]
}
```

### not

Negates a condition.

**Required fields:** `type`, `condition`

```python
{
    "type": "not",
    "condition": {"type": "condition", "field": "status", "op": "==", "value": "blocked"}
}
```

### exists, sequence, accumulate

Additional node types for advanced features (documented in [Nested Facts](nested-facts.md) and [Working Memory](working-memory.md)).

---

## Validation Modes

The validation happens automatically at rule creation. If validation fails, behavior depends on context:

- **Rule creation in code**: Validate explicitly before use
- **REST API**: Validation is automatic (returns 400 Bad Request on error)
- **YAML loader**: Validation is automatic (raises exception on error)
- **Engine load**: No validation (assumes rules are pre-validated)

---

## Examples

### Using the Shared Dataset

The shared payment-risk dataset includes a validation example in [Example 04](examples.md):

```python
from fluxrules.domain.dsl.validation import DSLValidationError, validate_dsl

# Validate a nested condition tree
nested_condition = {
    "type": "group",
    "op": "AND",
    "children": [
        {"type": "condition", "field": "amount", "op": ">", "value": 5000},
        {"type": "group", "op": "OR", "children": [
            {"type": "condition", "field": "country", "op": "in", "value": ["CN", "RU"]},
            {"type": "condition", "field": "ip_risk_score", "op": ">=", "value": 85}
        ]}
    ]
}

validate_dsl(nested_condition)  # ✅ Passes
```

See [Example 04: Validation](https://github.com/saurabh2mishra/fluxrules/blob/main/examples/04_validation.py) for complete working code.

For error handling with validation, see [Example 14: Error Handling](https://github.com/saurabh2mishra/fluxrules/blob/main/examples/14_error_handling.py).

---

## DSL Validation Errors

When validation fails, you get a `DSLValidationError` with context about what went wrong.

**Example: Invalid operator**

```python
from fluxrules.domain.dsl.validation import validate_dsl, DSLValidationError

try:
    validate_dsl({
        "type": "condition",
        "field": "amount",
        "op": "is_greater_than",  # ❌ Not a valid operator
        "value": 100
    })
except DSLValidationError as e:
    print(e)  # "is_greater_than is not a valid operator..."
```

**Example: Missing required field**

```python
try:
    validate_dsl({
        "type": "condition",
        "field": "amount"
        # ❌ Missing 'op' and 'value'
    })
except DSLValidationError as e:
    print(e)  # "Condition missing required 'op' key"
```

---

## Valid Operators Reference

The 10 valid operators are:

| Operator | Type | Example | Use Case |
|----------|------|---------|----------|
| `==` | Equality | `"op": "=="` | Exact match |
| `!=` | Inequality | `"op": "!="` | Not equal |
| `>` | Greater than | `"op": ">"` | Greater than (numeric) |
| `>=` | Greater or equal | `"op": ">="` | Greater or equal (numeric) |
| `<` | Less than | `"op": "<"` | Less than (numeric) |
| `<=` | Less or equal | `"op": "<="` | Less or equal (numeric) |
| `in` | Membership | `"op": "in", "value": [...]` | One of multiple values |
| `not_in` | Non-membership | `"op": "not_in", "value": [...]` | Not in list |
| `contains` | String contains | `"op": "contains"` | Substring match |
| `not_contains` | String doesn't contain | `"op": "not_contains"` | Substring not found |

**Source:** `src/fluxrules/engine/operators.py` (VALID_OPERATORS)

---

## When Validation Happens

- **Explicit call**: `validate_dsl(dsl)` - synchronous, raises on error
- **Rule creation**: Rules are structurally validated on instantiation
- **Engine load**: No automatic validation (`engine.load_rules()` assumes pre-validated rules)
- **REST API** (if enabled): Automatic validation before saving
- **YAML loader** (if enabled): Automatic validation on load

---

## Limitations

**What validation covers:**
- ✅ DSL syntax and structure
- ✅ Operator validity
- ✅ Required fields
- ✅ Type checking (values match operator expectations)

**What validation does NOT cover:**
- ❌ Semantic logic (does your business rule make sense?)
- ❌ Dead rule detection (rules that can never match)
- ❌ Rule conflicts (multiple rules matching same input)
- ❌ Coverage gaps (uncovered input spaces)

For advanced validation, use manual review or rule analysis tools (see [Rule Analysis](rule-analysis.md)).

---

## Next Steps

- **[Complex Conditions](complex-conditions.md)** - Nested AND/OR/NOT logic
- **[Conditions Reference](conditions.md)** - All operators explained
- **[Error Handling](https://github.com/saurabh2mishra/fluxrules/blob/main/examples/14_error_handling.py)** - Catch validation errors in code
- **[Examples 04 & 14](examples.md)** - Working validation examples
