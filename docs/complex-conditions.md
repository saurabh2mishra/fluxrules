# Complex Conditions

Combine multiple simple conditions using AND/OR/NOT logic.

**Prerequisites:** [Conditions & Operators](conditions.md) (condition syntax and operators).

**Source:** `src/fluxrules/domain/dsl/` (DSL structure and validation)

---

## What is a Complex Condition?

A complex condition combines two or more simple conditions using logical operators. They answer multi-part questions:

- "Is the amount > $2000 **AND** is the country in [NG, SN]?"
- "Is account age < 7 days **OR** is IP risk score >= 70?"
- "Is **NOT** a verified user?"

---

## AND Logic

All conditions must be true for the group to match.

**Format:**
```python
{
    "type": "group",
    "op": "AND",
    "children": [
        {"type": "condition", "field": "amount", "op": ">", "value": 2000},
        {"type": "condition", "field": "country", "op": "in", "value": ["NG", "SN"]},
    ]
}
```

**Example Rule:**
```python
from fluxrules import Rule, PhreakEngine

rule = Rule(
    name="high_value_international",
    condition_dsl={
        "type": "group",
        "op": "AND",
        "children": [
            {"type": "condition", "field": "amount", "op": ">", "value": 5000},
            {"type": "condition", "field": "country", "op": "not_in", "value": ["US", "CA", "GB"]},
        ]
    },
    action="manual_review",
)

engine = PhreakEngine()
engine.load_rules([rule])

# Matches (both conditions true)
fact1 = {"amount": 6000, "country": "NG"}
print(engine.evaluate(fact1).fired_rules)  # [1]

# Does not match (amount too low)
fact2 = {"amount": 3000, "country": "NG"}
print(engine.evaluate(fact2).fired_rules)  # []
```

---

## OR Logic

At least one condition must be true for the group to match.

**Format:**
```python
{
    "type": "group",
    "op": "OR",
    "children": [
        {"type": "condition", "field": "amount", "op": ">", "value": 2000},
        {"type": "condition", "field": "velocity_1h", "op": ">=", "value": 5},
    ]
}
```

**Example Rule:**
```python
rule = Rule(
    name="risky_pattern",
    condition_dsl={
        "type": "group",
        "op": "OR",
        "children": [
            {"type": "condition", "field": "amount", "op": ">", "value": 5000},
            {"type": "condition", "field": "velocity_1h", "op": ">=", "value": 5},
            {"type": "condition", "field": "ip_risk_score", "op": ">=", "value": 80},
        ]
    },
    action="block_payment",
)

engine = PhreakEngine()
engine.load_rules([rule])

# Matches (high amount)
fact1 = {"amount": 6000, "velocity_1h": 1, "ip_risk_score": 30}
print(engine.evaluate(fact1).fired_rules)  # [1]

# Matches (high velocity)
fact2 = {"amount": 1000, "velocity_1h": 6, "ip_risk_score": 30}
print(engine.evaluate(fact2).fired_rules)  # [1]

# Does not match (all below thresholds)
fact3 = {"amount": 1000, "velocity_1h": 1, "ip_risk_score": 30}
print(engine.evaluate(fact3).fired_rules)  # []
```

---

## NOT Logic

Negates a condition (the condition must be false).

**Format:**
```python
{
    "type": "not",
    "condition": {
        "type": "condition",
        "field": "verified_user",
        "op": "==",
        "value": True
    }
}
```

**Example Rule:**
```python
rule = Rule(
    name="unverified_high_value",
    condition_dsl={
        "type": "group",
        "op": "AND",
        "children": [
            {"type": "condition", "field": "amount", "op": ">", "value": 2000},
            {
                "type": "not",
                "condition": {
                    "type": "condition",
                    "field": "email_domain",
                    "op": "ends_with",
                    "value": "trusted.com"
                }
            },
        ]
    },
    action="step_up_auth",
)

engine = PhreakEngine()
engine.load_rules([rule])

# Matches (high amount AND not from trusted domain)
fact1 = {"amount": 3000, "email_domain": "gmail.com"}
print(engine.evaluate(fact1).fired_rules)  # [1]

# Does not match (email from trusted domain)
fact2 = {"amount": 3000, "email_domain": "trusted.com"}
print(engine.evaluate(fact2).fired_rules)  # []
```

---

## Nested Logic (Complex Combinations)

Combine AND, OR, and NOT for sophisticated logic:

```python
rule = Rule(
    name="payment_risk_triage",
    condition_dsl={
        "type": "group",
        "op": "AND",
        "children": [
            # Part 1: Large amount
            {"type": "condition", "field": "amount", "op": ">", "value": 2000},
            
            # Part 2: High-risk country OR high IP risk
            {
                "type": "group",
                "op": "OR",
                "children": [
                    {"type": "condition", "field": "country", "op": "in", "value": ["NG", "SN", "GH"]},
                    {"type": "condition", "field": "ip_risk_score", "op": ">=", "value": 70},
                ]
            },
            
            # Part 3: New or unverified account
            {
                "type": "group",
                "op": "OR",
                "children": [
                    {"type": "condition", "field": "account_age_days", "op": "<", "value": 7},
                    {"type": "condition", "field": "device_age_days", "op": "<", "value": 7},
                ]
            },
            
            # Part 4: NOT a trusted email
            {
                "type": "not",
                "condition": {
                    "type": "condition",
                    "field": "email_domain",
                    "op": "ends_with",
                    "value": "trusted.example"
                }
            },
        ]
    },
    action="manual_review",
)
```

**Logic:**
1. Amount must be > $2000
2. AND (country is high-risk OR IP risk >= 70)
3. AND (account age < 7 days OR device age < 7 days)
4. AND (NOT from trusted.example domain)

---

## Real-World Example

All examples demonstrate nested logic:

- **[02_complex_conditions.py](https://github.com/fluxrules/fluxrules/blob/main/examples/02_complex_conditions.py)** - Nested boolean logic
- **[13_complex_rules.py](https://github.com/fluxrules/fluxrules/blob/main/examples/13_complex_rules.py)** - 8-condition complex payment rule

**Run:**
```bash
cd examples
python 02_complex_conditions.py
```

---

## Operator Precedence

**Order of evaluation:** NOT > AND > OR (when mixing operators)

When in doubt, use explicit nesting with `type: "group"`.

---

## Next Steps

- **[Conditions](conditions.md)** - Simple operator reference
- **[Validation Framework](validation-framework.md)** - Validate DSL structures
- **[Concepts](concepts.md)** - Understanding the DSL


When combining conditions, precedence works like mathematical expressions:

```
AND has higher precedence than OR

(A OR B) AND C  means:  Only if (A or B is true) AND (C is true)
A OR (B AND C)  means:  Either A is true, or (B and C are both true)
```

### Explicit Grouping
Use nested structures to be explicit about precedence:

```python
from fluxrules import Rule

# Scenario: "Gold members OR (new customers with high purchase intent)"
rule = Rule(
    name="Special Retention Offer",
    condition_dsl={
        'type': 'group', 'op': 'OR', 'children': [
            # Group 1: Existing loyal customers
            {'type': 'condition', 'field': 'membership_level', 'op': '==', 'value': 'gold'},
            # Group 2: New customers with high purchase intent
            {'type': 'group', 'op': 'AND', 'children': [
                {'type': 'condition', 'field': 'is_new_customer', 'op': '==', 'value': True},
                {'type': 'condition', 'field': 'cart_value', 'op': '>', 'value': 500},
                {'type': 'condition', 'field': 'browse_time_minutes', 'op': '>', 'value': 10},
            ]},
        ]
    },
    action="premium_discount",
)
```

## Practical Examples

### Example 1: Loan Approval
Approve loans based on credit and income criteria:

```python
from fluxrules import Rule

rule = Rule(
    name="Fast Track Loan Approval",
    condition_dsl={
        'type': 'group', 'op': 'AND', 'children': [
            {'type': 'condition', 'field': 'credit_score', 'op': '>=', 'value': 750},
            {'type': 'condition', 'field': 'debt_to_income_ratio', 'op': '<=', 'value': 0.4},
            {'type': 'group', 'op': 'OR', 'children': [
                {'type': 'condition', 'field': 'employment_years', 'op': '>=', 'value': 3},
                {'type': 'condition', 'field': 'annual_income', 'op': '>', 'value': 100000},
            ]},
        ]
    },
    action="fast_track_approved",
)
```

### Example 2: Email Campaign Targeting
Target specific customer segments:

```python
from fluxrules import Rule

rule = Rule(
    name="Send Summer Sale Email",
    condition_dsl={
        'type': 'group', 'op': 'AND', 'children': [
            # Must be active and opted-in
            {'type': 'condition', 'field': 'account_status', 'op': '==', 'value': 'active'},
            {'type': 'condition', 'field': 'email_opted_in', 'op': '==', 'value': True},
            # Either high-value or seasonal buyer
            {'type': 'group', 'op': 'OR', 'children': [
                {'type': 'condition', 'field': 'annual_spend', 'op': '>', 'value': 1000},
                {'type': 'condition', 'field': 'summer_purchases_count', 'op': '>', 'value': 2},
            ]},
            # Not recently emailed
            {'type': 'condition', 'field': 'days_since_last_email', 'op': '>', 'value': 7},
        ]
    },
    action="send_summer_sale_email",
)
```

### Example 3: Inventory Management
Trigger different actions based on stock levels:

```python
from fluxrules import Rule, PhreakEngine

reorder_rule = Rule(
    name="Reorder Low Stock Items",
    condition_dsl={
        'type': 'group', 'op': 'AND', 'children': [
            {'type': 'condition', 'field': 'stock_quantity', 'op': '<', 'value': 50},
            {'type': 'group', 'op': 'OR', 'children': [
                {'type': 'condition', 'field': 'is_bestseller', 'op': '==', 'value': True},
                {'type': 'condition', 'field': 'stock_out_days', 'op': '>', 'value': 3},
            ]},
            {'type': 'condition', 'field': 'supplier_available', 'op': '==', 'value': True},
        ]
    },
    action="reorder",
)

discontinue_rule = Rule(
    name="Discontinue Slow-Moving Items",
    condition_dsl={
        'type': 'group', 'op': 'AND', 'children': [
            {'type': 'condition', 'field': 'stock_quantity', 'op': '>', 'value': 200},
            {'type': 'condition', 'field': 'units_sold_annual', 'op': '<', 'value': 10},
            {'type': 'condition', 'field': 'list_price', 'op': '<', 'value': 5},
        ]
    },
    action="discontinue",
)

engine = PhreakEngine()
engine.load_rules([reorder_rule, discontinue_rule])
```

### Example 4: Premium Feature Access
Grant features based on subscription and usage:

```python
from fluxrules import Rule

rule = Rule(
    name="Grant Advanced Analytics Access",
    condition_dsl={
        'type': 'group', 'op': 'AND', 'children': [
            # Must have active subscription
            {'type': 'condition', 'field': 'subscription_status', 'op': '==', 'value': 'active'},
            # Must be on Pro plan or higher
            {'type': 'group', 'op': 'OR', 'children': [
                {'type': 'condition', 'field': 'plan_type', 'op': 'in', 'value': ['pro', 'enterprise']},
                # OR free tier but heavy user
                {'type': 'group', 'op': 'AND', 'children': [
                    {'type': 'condition', 'field': 'plan_type', 'op': '==', 'value': 'free'},
                    {'type': 'condition', 'field': 'api_calls_monthly', 'op': '>', 'value': 100000},
                ]},
            ]},
            # Not suspended
            {'type': 'condition', 'field': 'is_suspended', 'op': '==', 'value': False},
        ]
    },
    action="grant_advanced_analytics",
)
```

## Boolean Operations Reference

### De Morgan's Laws
When negating complex conditions, remember:

```
NOT (A AND B)  ≡  (NOT A) OR (NOT B)
NOT (A OR B)   ≡  (NOT A) AND (NOT B)
```

**Example:** Instead of checking if NOT (is_active AND in_US), check if (is_inactive OR not_in_US).

## Building Complex Conditions Programmatically

```python
from fluxrules import Rule, PhreakEngine

# Build sub-conditions step by step, then compose them
credit_check = {
    'type': 'group', 'op': 'AND',
    'children': [
        {'type': 'condition', 'field': 'credit_score', 'op': '>=', 'value': 700},
        {'type': 'condition', 'field': 'credit_inquiries_30days', 'op': '<', 'value': 3},
    ]
}

income_check = {
    'type': 'condition', 'field': 'annual_income', 'op': '>=', 'value': 50000
}

employment_check = {
    'type': 'group', 'op': 'OR',
    'children': [
        {'type': 'condition', 'field': 'employment_status', 'op': '==', 'value': 'employed'},
        {'type': 'condition', 'field': 'is_self_employed', 'op': '==', 'value': True},
        {'type': 'condition', 'field': 'retirement_account_balance', 'op': '>', 'value': 200000},
    ]
}

# Combine them into a Rule
rule = Rule(
    name="Credit Card Approval",
    condition_dsl={
        'type': 'group', 'op': 'AND',
        'children': [credit_check, income_check, employment_check],
    },
    action="approve_card",
)

engine = PhreakEngine()
engine.load_rules([rule])
```

## Testing Complex Conditions

### Test Individual Segments
```python
# Test credit segment only
test_facts = {
    'credit_score': 750,
    'credit_inquiries_30days': 1,
    'annual_income': 75000,
    'employment_status': 'employed'
}

results = engine.evaluate(test_facts)
```

### Use Debug Mode
```python
engine = PhreakEngine()
results = engine.evaluate(test_facts)
# Engine will log each condition evaluation
```

### Test Boundary Cases
```python
# Test at exact boundaries
boundary_cases = [
    {'credit_score': 700},      # Exactly minimum
    {'credit_score': 699},      # Just below minimum
    {'annual_income': 50000},   # Exactly minimum
    {'annual_income': 49999},   # Just below minimum
]

for fact in boundary_cases:
    results = engine.evaluate(fact)
    print(f"Facts: {fact}, Matched: {results.fired_rules}")
```

## Best Practices

### 1. Keep Conditions Readable
```python
# Good: Easy to understand intent
{'type': 'group', 'op': 'AND', 'children': [
    {'type': 'condition', 'field': 'age', 'op': '>=', 'value': 18},
    {'type': 'condition', 'field': 'has_drivers_license', 'op': '==', 'value': True}
]}

# Harder to read: Too nested
{'type': 'group', 'op': 'OR', 'children': [
    {'type': 'group', 'op': 'AND', 'children': [
        {'type': 'group', 'op': 'OR', 'children': [...]},
        {'type': 'group', 'op': 'AND', 'children': [...]}
    ]},
    ...
]}
```

### 2. Use Semantic Grouping
Group related conditions together:

```python
# Good: Grouped by concept
{
    'type': 'group', 'op': 'AND',
    'children': [
        # Account verification
        {'type': 'group', 'op': 'AND', 'children': [
            {'type': 'condition', 'field': 'email_verified', 'op': '==', 'value': True},
            {'type': 'condition', 'field': 'phone_verified', 'op': '==', 'value': True}
        ]},
        # Payment method
        {'type': 'group', 'op': 'OR', 'children': [
            {'type': 'condition', 'field': 'has_credit_card', 'op': '==', 'value': True},
            {'type': 'condition', 'field': 'has_bank_account', 'op': '==', 'value': True}
        ]}
    ]
}
```

### 3. Avoid Redundancy
```python
# Good: Simple and clear
{'type': 'group', 'op': 'AND', 'children': [
    {'type': 'condition', 'field': 'age', 'op': '>=', 'value': 18},
    {'type': 'condition', 'field': 'country', 'op': 'in', 'value': ['US', 'CA', 'UK']}
]}

# Redundant: age >= 18 AND age >= 0 is unnecessary
{'type': 'group', 'op': 'AND', 'children': [
    {'type': 'condition', 'field': 'age', 'op': '>=', 'value': 18},
    {'type': 'condition', 'field': 'age', 'op': '>=', 'value': 0}
]}
```

### 4. Document Complex Logic
```python
from fluxrules import Rule

# Grant special pricing if (new customer OR loyal customer) AND (high order value)
rule = Rule(
    name="Apply Special Pricing",
    description="Grant special pricing if (new customer OR loyal customer) AND (high order value)",
    condition_dsl={
        'type': 'group', 'op': 'AND', 'children': [
            # New OR loyal customers
            {'type': 'group', 'op': 'OR', 'children': [
                {'type': 'condition', 'field': 'days_as_customer', 'op': '<', 'value': 30},
                {'type': 'condition', 'field': 'lifetime_purchases', 'op': '>', 'value': 10000},
            ]},
            # With significant orders
            {'type': 'condition', 'field': 'current_order_value', 'op': '>', 'value': 500},
        ]
    },
    action="apply_special_pricing",
)
```

## Next Steps

- **[Domains & Tags](domains-and-tags.md)** - Organize complex rules at scale
- **[Validation Framework](validation-framework.md)** - Ensure your conditions are valid
- **[Working Memory](working-memory.md)** - Use state to build multi-step logic
