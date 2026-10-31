# Validation Framework

Validation in FluxRules catches errors in condition logic before rules are deployed.

**Prerequisites:** Familiarity with [Conditions](conditions.md) and condition condition tree structure (see [Complex Conditions](complex-conditions.md)).

---

## What Gets Validated

When you create or load rules, FluxRules validates the condition tree:

- **Syntax**: Structure, types, required fields
- **Semantics**: Valid operators, valid values
- **Logic**: No impossible conditions (e.g., `age > 18 AND age < 18`)

The validation system catches errors early with clear error messages.

**Source:** `src/fluxrules/domain/conditions/validation.py`

---

## How to Validate

### Validate a Single Rule's Conditions

```python
from fluxrules.domain.conditions.validation import validate_conditions, ConditionValidationError
from fluxrules.domain import Rule

# Define a rule: F DSL is the recommended authoring format
from fluxrules import F

rule = Rule(
    name="high_amount_check",
    conditions=(F("amount") > 5000) & (F("country").isin(["US", "CA"])),
    action="review",
)

# Validate the condition tree
try:
    validate_conditions(rule.conditions)
    print("✓ Rule is valid")
except ConditionValidationError as e:
    print(f"✗ Validation error: {e}")
```

### Common Validation Errors

These examples are written as dictionaries on purpose: `F` expressions can only
build valid nodes, so a hand-written dictionary is how an invalid one appears.

**Invalid operator:**
```python
invalid_dsl = {
    "type": "condition",
    "field": "amount",
    "op": "__unknown__",  # ✗ Not in VALID_OPERATORS
    "value": 100
}
# Raises: ConditionValidationError: '__unknown__' is not a valid operator
```

**Impossible logic:**
```python
impossible_dsl = {
    "type": "group",
    "op": "AND",
    "children": [
        {"type": "condition", "field": "age", "op": ">", "value": 18},
        {"type": "condition", "field": "age", "op": "<", "value": 18}  # ✗ Impossible
    ]
}
# Note: validate_conditions validates structure; dead-rule detection is on the roadmap
```

**Missing required fields:**
```python
invalid_condition = {
    "type": "condition",
    "field": "amount"
    # ✗ Missing 'op' and 'value'
}
# Raises: ConditionValidationError: missing required 'op' key
```

---

## Condition Node Types and Validation Rules

### condition

Tests a single field against a value using an operator.

**Required fields:** `type`, `field`, `op`, `value`

**Valid operators:** `==`, `!=`, `>`, `>=`, `<`, `<=`, `in`, `not_in`, `contains`, `not_contains`

```python
from fluxrules import F

F("amount") >= 1000
# stored as:
{"type": "condition", "field": "amount", "op": ">=", "value": 1000}
```

### group

Combines multiple conditions with AND or OR logic.

**Required fields:** `type`, `op`, `children`

**Valid op values:** `"AND"`, `"OR"` (case-insensitive; both uppercase and lowercase work)

```python
from fluxrules import F

(F("amount") > 100) & (F("status") == "active")
# stored as:
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
from fluxrules import F

~(F("status") == "blocked")
# stored as:
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
from fluxrules import F, Rule, validate
from fluxrules.domain.conditions.validation import ConditionValidationError, validate_conditions

# Author with F DSL, validate with the top-level API
rule = Rule(
    name="fraud_check",
    conditions=(
        (F("amount") > 5000)
        & (
            (F("country").isin(["CN", "RU"]))
            | (F("ip_risk_score") >= 85)
        )
    ),
    action="block",
)

issues = validate([rule])
assert issues == []  # ✓ Passes

# Or validate the underlying condition tree directly
validate_conditions(rule.conditions)  # ✓ Passes
```

See [Example 04: Validation](https://github.com/saurabh2mishra/fluxrules/blob/main/examples/04_validation.py) for complete working code.

For error handling with validation, see [Example 14: Error Handling](https://github.com/saurabh2mishra/fluxrules/blob/main/examples/14_error_handling.py).

---

## Condition Validation Errors

When validation fails, you get a `ConditionValidationError` with context about what went wrong.

**Example: Invalid operator**

```python
from fluxrules.domain.conditions.validation import validate_conditions, ConditionValidationError

try:
    validate_conditions({
        "type": "condition",
        "field": "amount",
        "op": "is_greater_than",  # ✗ Not a valid operator
        "value": 100
    })
except ConditionValidationError as e:
    print(e)  # "is_greater_than is not a valid operator..."
```

**Example: Missing required field**

```python
try:
    validate_conditions({
        "type": "condition",
        "field": "amount"
        # ✗ Missing 'op' and 'value'
    })
except ConditionValidationError as e:
    print(e)  # "Condition missing required 'op' key"
```

---

## Valid Operators Reference

The 13 valid operators are below. The comparison operators also accept the word
aliases `eq`, `ne`, `gt`, `gte`, `lt` and `lte` in dictionary and YAML rules.

| `"op"` | F expression | Use case |
|--------|--------------|----------|
| `==` | `F("x") == v` | Exact match |
| `!=` | `F("x") != v` | Not equal |
| `>` | `F("x") > v` | Greater than (numeric) |
| `>=` | `F("x") >= v` | Greater or equal (numeric) |
| `<` | `F("x") < v` | Less than (numeric) |
| `<=` | `F("x") <= v` | Less or equal (numeric) |
| `in` | `F("x").isin([...])` | One of several values |
| `not_in` | `F("x").not_in([...])` | Not one of several values |
| `contains` | `F("x").contains(v)` | Collection or string contains a value |
| `not_contains` | `F("x").not_contains(v)` | Does not contain a value |
| `starts_with` | `F("x").starts_with(v)` | String prefix |
| `ends_with` | `F("x").ends_with(v)` | String suffix |
| `regex` | `F("x").regex(p)` | Regular expression match |

**Source:** `src/fluxrules/engine/operators.py` (VALID_OPERATORS)

---

## When Validation Happens

- **Explicit call**: `validate_conditions(dsl)`, synchronous, raises on error
- **Rule creation**: Rules are structurally validated on instantiation
- **Engine load**: No automatic validation (`engine.load_rules()` assumes pre-validated rules)
- **REST API** (if enabled): Automatic validation before saving
- **YAML loader** (if enabled): Automatic validation on load

---

## Limitations

**What validation covers:**
- ✓ condition tree syntax and structure
- ✓ Operator validity
- ✓ Required fields
- ✓ Type checking (values match operator expectations)

**What validation does NOT cover:**
- ✗ Semantic logic (does your business rule make sense?)
- ✗ Dead rule detection (rules that can never match)
- ✗ Rule conflicts (multiple rules matching same input)
- ✗ Coverage gaps (uncovered input spaces)

For advanced validation, use manual review or rule analysis tools (see [Rule Analysis](rule-analysis.md)).

---

## Next Steps

- **[Complex Conditions](complex-conditions.md)**: Nested AND/OR/NOT logic
- **[Conditions Reference](conditions.md)**: All operators explained
- **[Error Handling](https://github.com/saurabh2mishra/fluxrules/blob/main/examples/14_error_handling.py)**: Catch validation errors in code
- **[Examples 04 & 14](examples.md)**: Working validation examples
