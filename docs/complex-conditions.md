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
from fluxrules.domain import Rule
from fluxrules.engine.phreak import PhreakEngine

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

- **[02_complex_conditions.py](https://github.com/fluxrules/fluxrules/blob/main/examples/02_complex_conditions.py)** — Nested boolean logic
- **[13_complex_rules.py](https://github.com/fluxrules/fluxrules/blob/main/examples/13_complex_rules.py)** — 8-condition complex payment rule

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

- **[Conditions](conditions.md)** — Simple operator reference
- **[Validation Framework](validation-framework.md)** — Validate DSL structures
- **[Concepts](concepts.md)** — Understanding the DSL


When combining conditions, precedence works like mathematical expressions:

```
AND has higher precedence than OR

(A OR B) AND C  means:  Only if (A or B is true) AND (C is true)
A OR (B AND C)  means:  Either A is true, or (B and C are both true)
```

### Explicit Grouping
Use nested structures to be explicit about precedence:

```python
# Scenario: "Gold members OR (new customers with high purchase intent)"
rule = {
    'id': 'retention_offer',
    'name': 'Special Retention Offer',
    'conditions': [
        {'type': 'or', 'conditions': [
            # Group 1: Existing loyal customers
            {'attribute': 'membership_level', 'operator': '==', 'value': 'gold'},
            # Group 2: New customers with high purchase intent
            {'type': 'and', 'conditions': [
                {'attribute': 'is_new_customer', 'operator': '==', 'value': True},
                {'attribute': 'cart_value', 'operator': '>', 'value': 500},
                {'attribute': 'browse_time_minutes', 'operator': '>', 'value': 10}
            ]}
        ]}
    ],
    'actions': [
        {'action': 'set', 'target': 'offer_type', 'value': 'premium_discount'}
    ]
}
```

## Practical Examples

### Example 1: Loan Approval
Approve loans based on credit and income criteria:

```python
rule = {
    'id': 'loan_approval',
    'name': 'Fast Track Loan Approval',
    'conditions': [
        {'type': 'and', 'conditions': [
            {'attribute': 'credit_score', 'operator': '>=', 'value': 750},
            {'attribute': 'debt_to_income_ratio', 'operator': '<=', 'value': 0.4},
            {'type': 'or', 'conditions': [
                {'attribute': 'employment_years', 'operator': '>=', 'value': 3},
                {'attribute': 'annual_income', 'operator': '>', 'value': 100000}
            ]}
        ]}
    ],
    'actions': [
        {'action': 'set', 'target': 'approval_status', 'value': 'approved'},
        {'action': 'set', 'target': 'processing_priority', 'value': 'fast_track'}
    ]
}
```

### Example 2: Email Campaign Targeting
Target specific customer segments:

```python
rule = {
    'id': 'summer_sale_email',
    'name': 'Send Summer Sale Email',
    'conditions': [
        {'type': 'and', 'conditions': [
            # Must be active and opted-in
            {'attribute': 'account_status', 'operator': '==', 'value': 'active'},
            {'attribute': 'email_opted_in', 'operator': '==', 'value': True},
            # Either high-value or seasonal buyer
            {'type': 'or', 'conditions': [
                {'attribute': 'annual_spend', 'operator': '>', 'value': 1000},
                {'attribute': 'summer_purchases_count', 'operator': '>', 'value': 2}
            ]},
            # Not recently emailed
            {'attribute': 'days_since_last_email', 'operator': '>', 'value': 7}
        ]}
    ],
    'actions': [
        {'action': 'set', 'target': 'send_email', 'value': True},
        {'action': 'set', 'target': 'campaign_name', 'value': 'summer_sale_2024'}
    ]
}
```

### Example 3: Inventory Management
Trigger different actions based on stock levels:

```python
engine = PhreakEngine()

# Reorder rule
engine.add_rule({
    'id': 'reorder_stock',
    'name': 'Reorder Low Stock Items',
    'conditions': [
        {'type': 'and', 'conditions': [
            {'attribute': 'stock_quantity', 'operator': '<', 'value': 50},
            {'type': 'or', 'conditions': [
                {'attribute': 'is_bestseller', 'operator': '==', 'value': True},
                {'attribute': 'stock_out_days', 'operator': '>', 'value': 3}
            ]},
            {'attribute': 'supplier_available', 'operator': '==', 'value': True}
        ]}
    ],
    'actions': [
        {'action': 'set', 'target': 'action', 'value': 'reorder'},
        {'action': 'set', 'target': 'quantity', 'value': 100}
    ]
})

# Discontinue rule
engine.add_rule({
    'id': 'discontinue_item',
    'name': 'Discontinue Slow-Moving Items',
    'conditions': [
        {'type': 'and', 'conditions': [
            {'attribute': 'stock_quantity', 'operator': '>', 'value': 200},
            {'attribute': 'units_sold_annual', 'operator': '<', 'value': 10},
            {'attribute': 'list_price', 'operator': '<', 'value': 5}
        ]}
    ],
    'actions': [
        {'action': 'set', 'target': 'action', 'value': 'discontinue'}
    ]
})
```

### Example 4: Premium Feature Access
Grant features based on subscription and usage:

```python
rule = {
    'id': 'advanced_analytics',
    'name': 'Grant Advanced Analytics Access',
    'conditions': [
        {'type': 'and', 'conditions': [
            # Must have active subscription
            {'attribute': 'subscription_status', 'operator': '==', 'value': 'active'},
            # Must be on Pro plan or higher
            {'type': 'or', 'conditions': [
                {'attribute': 'plan_type', 'operator': 'in', 'value': ['pro', 'enterprise']},
                # OR free tier but heavy user
                {'type': 'and', 'conditions': [
                    {'attribute': 'plan_type', 'operator': '==', 'value': 'free'},
                    {'attribute': 'api_calls_monthly', 'operator': '>', 'value': 100000}
                ]}
            ]},
            # Not suspended
            {'attribute': 'is_suspended', 'operator': '==', 'value': False}
        ]}
    ],
    'actions': [
        {'action': 'set', 'target': 'feature_enabled', 'value': True}
    ]
}
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
from fluxrules import PhreakEngine

engine = PhreakEngine()

# Build conditions step by step
credit_check = {
    'type': 'and',
    'conditions': [
        {'attribute': 'credit_score', 'operator': '>=', 'value': 700},
        {'attribute': 'credit_inquiries_30days', 'operator': '<', 'value': 3}
    ]
}

income_check = {
    'attribute': 'annual_income',
    'operator': '>=',
    'value': 50000
}

employment_check = {
    'type': 'or',
    'conditions': [
        {'attribute': 'employment_status', 'operator': '==', 'value': 'employed'},
        {'attribute': 'is_self_employed', 'operator': '==', 'value': True},
        {'attribute': 'retirement_account_balance', 'operator': '>', 'value': 200000}
    ]
}

# Combine them
rule = {
    'id': 'credit_card_approval',
    'name': 'Credit Card Approval',
    'conditions': [
        {'type': 'and', 'conditions': [
            credit_check,
            income_check,
            employment_check
        ]}
    ],
    'actions': [
        {'action': 'set', 'target': 'card_approved', 'value': True}
    ]
}

engine.add_rule(rule)
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
{'type': 'and', 'conditions': [
    {'attribute': 'age', 'operator': '>=', 'value': 18},
    {'attribute': 'has_drivers_license', 'operator': '==', 'value': True}
]}

# Harder to read: Too nested
{'type': 'or', 'conditions': [
    {'type': 'and', 'conditions': [
        {'type': 'or', 'conditions': [...]},
        {'type': 'and', 'conditions': [...]}
    ]},
    ...
]}
```

### 2. Use Semantic Grouping
Group related conditions together:

```python
# Good: Grouped by concept
{
    'type': 'and',
    'conditions': [
        # Account verification
        {'type': 'and', 'conditions': [
            {'attribute': 'email_verified', 'operator': '==', 'value': True},
            {'attribute': 'phone_verified', 'operator': '==', 'value': True}
        ]},
        # Payment method
        {'type': 'or', 'conditions': [
            {'attribute': 'has_credit_card', 'operator': '==', 'value': True},
            {'attribute': 'has_bank_account', 'operator': '==', 'value': True}
        ]}
    ]
}
```

### 3. Avoid Redundancy
```python
# Good: Simple and clear
{'type': 'and', 'conditions': [
    {'attribute': 'age', 'operator': '>=', 'value': 18},
    {'attribute': 'country', 'operator': 'in', 'value': ['US', 'CA', 'UK']}
]}

# Redundant: age >= 18 AND age >= 0 is unnecessary
{'type': 'and', 'conditions': [
    {'attribute': 'age', 'operator': '>=', 'value': 18},
    {'attribute': 'age', 'operator': '>=', 'value': 0}
]}
```

### 4. Document Complex Logic
```python
rule = {
    'id': 'special_pricing',
    'name': 'Apply Special Pricing',
    'description': 'Grant special pricing if (new customer OR loyal customer) AND (high order value)',
    'conditions': [
        {'type': 'and', 'conditions': [
            # New OR loyal customers
            {'type': 'or', 'conditions': [
                {'attribute': 'days_as_customer', 'operator': '<', 'value': 30},
                {'attribute': 'lifetime_purchases', 'operator': '>', 'value': 10000}
            ]},
            # With significant orders
            {'attribute': 'current_order_value', 'operator': '>', 'value': 500}
        ]}
    ]
}
```

## Next Steps

- **[Domains & Tags](domains-and-tags.md)** - Organize complex rules at scale
- **[Validation Framework](validation-framework.md)** - Ensure your conditions are valid
- **[Working Memory](working-memory.md)** - Use state to build multi-step logic
