# Core Concepts

This page introduces the fundamental concepts you need to work with FluxRules. All code references are to `src/fluxrules/`.

---

## Rule

A **Rule** is the core abstraction. It combines a condition, an action, and metadata for organization.

**Source:** `src/fluxrules/domain/unified_rule.py`

```python
from fluxrules import Rule

rule = Rule(
    name="payment_risk_high",
    condition_dsl={
        "type": "condition",
        "field": "amount",
        "op": ">",
        "value": 5000,
    },
    action="manual_review",
    domain="fraud_detection",
    tags=frozenset(["tier_0", "high_value"]),
    priority=100,
)
```

**Key Attributes:**
- `id` — Auto-generated unique identifier (or manual override)
- `name` — Human-readable rule name
- `domain` — Logical grouping (e.g., "fraud_detection", "compliance")
- `tags` — String set for filtering and categorization
- `condition_dsl` — Nested tree defining when the rule fires
- `action` — What to do when the rule matches
- `priority` — Execution order (higher = runs first)

**See:** [examples/18_unified_rule.py](https://github.com/fluxrules/fluxrules/blob/main/examples/18_unified_rule.py)

---

## Engine

An **Engine** evaluates facts against loaded rules and returns matched rules and actions.

**Source:** `src/fluxrules/engine/` (interfaces and implementations)

A single engine is available:

- **PhreakEngine** (the only engine) — Lazy, agenda-driven evaluation with stateless (default) and streaming modes

**Quick Example:**
```python
from fluxrules import PhreakEngine

engine = PhreakEngine()
engine.load_rules([rule])

fact = {"amount": 6000, "country": "NG"}
result = engine.evaluate(fact)
```

**For evaluation modes**, see [The FluxRules Engine](engine-comparison.md).  
**For mode selection guidance**, see [Choosing an Evaluation Mode](choosing-an-engine.md).

---

## Fact

A **Fact** is a JSON-like dictionary representing data to evaluate against rules.

**Structure:** Flat or nested dictionaries
**Example:**
```python
fact = {
    "fact_id": "txn-001",
    "amount": 2500.00,
    "currency": "USD",
    "country": "NG",
    "ip_risk_score": 85,
    "velocity_1h": 3,
    "account_age_days": 7,
}
```

**Important:** A fact is **stateless** by default. Each `engine.evaluate(fact)` call is independent.

**See:** [examples/06_working_memory.py](https://github.com/fluxrules/fluxrules/blob/main/examples/06_working_memory.py) (state management patterns)

---

## Condition DSL

A **Condition DSL** (Domain-Specific Language) is a nested tree that defines when a rule fires. It combines:
- Simple conditions (field comparisons)
- Logical operators (AND, OR, NOT)
- Nested groups

**Basic condition:**
```python
{
    "type": "condition",
    "field": "amount",
    "op": ">",
    "value": 5000,
}
```

**Nested conditions (with AND/OR):**
```python
{
    "type": "group",
    "op": "AND",  # Both children must be true
    "children": [
        {"type": "condition", "field": "amount", "op": ">", "value": 5000},
        {"type": "condition", "field": "country", "op": "in", "value": ["NG", "SN"]},
    ]
}
```

**With NOT:**
```python
{
    "type": "not",
    "condition": {
        "type": "condition",
        "field": "email_domain",
        "op": "ends_with",
        "value": "trusted.com"
    }
}
```

**Validation:** Use `from fluxrules.domain.dsl.validation import validate_dsl`

**See:** [examples/02_complex_conditions.py](https://github.com/fluxrules/fluxrules/blob/main/examples/02_complex_conditions.py), [examples/13_complex_rules.py](https://github.com/fluxrules/fluxrules/blob/main/examples/13_complex_rules.py)

---

## Evaluation Result

When you evaluate a fact, the engine returns a result object with:

```python
result = engine.evaluate(fact)

# result.fired_rules — list of rule IDs that matched
# result.actions — list of actions to execute
# result.latency_ms — execution time in milliseconds
```

**Example:**
```python
print(f"Matched: {result.fired_rules}")  # [1001, 1003]
print(f"Actions: {result.actions}")       # ['manual_review', 'block_payment']
print(f"Time: {result.latency_ms}ms")     # 1.2ms
```

**See:** [examples/15_action_system.py](https://github.com/fluxrules/fluxrules/blob/main/examples/15_action_system.py)

---

## Domain

A **Domain** is a logical grouping of rules. Rules with the same domain typically handle a specific problem area.

**Common domains in payment risk:**
- `fraud_detection` — Anti-fraud rules
- `compliance` — Regulatory rules
- `risk_ops` — Risk assessment rules

**Filtering by domain:**
```python
from fluxrules import Rule, PhreakEngine

# Define rules with domains
rule1 = Rule(name="rule1", domain="fraud_detection", condition_dsl={"type": "condition", "field": "amount", "op": ">", "value": 5000}, action="flag")
rule2 = Rule(name="rule2", domain="compliance", condition_dsl={"type": "condition", "field": "country", "op": "==", "value": "NG"}, action="review")
rule3 = Rule(name="rule3", domain="fraud_detection", condition_dsl={"type": "condition", "field": "type", "op": "==", "value": "transaction"}, action="process")

all_rules = [rule1, rule2, rule3]

# Load only fraud_detection rules
fraud_rules = [r for r in all_rules if r.domain == "fraud_detection"]

engine = PhreakEngine()
engine.load_rules(fraud_rules)
```

**See:** [examples/03_domains_and_tags.py](https://github.com/fluxrules/fluxrules/blob/main/examples/03_domains_and_tags.py)

---

## Tag

A **Tag** is a string label for categorization and filtering.

**Typical tags:**
- `tier_0`, `tier_1`, `tier_2` — Rule priority tiers
- `cross_border` — Rules for cross-border scenarios
- `manual_review` — Rules requiring human review
- `auto_approve` — Rules for automatic approval

**Filtering by tag:**
```python
# Get all tier_0 rules
tier0_rules = [r for r in all_rules if "tier_0" in (r.tags or set())]
```

**See:** [examples/03_domains_and_tags.py](https://github.com/fluxrules/fluxrules/blob/main/examples/03_domains_and_tags.py)

---

## Shared Evaluation Dataset

To learn FluxRules, all examples use a shared `cross_border_payment_risk_triage` dataset:

```python
# python skip
from shared_use_case import SHARED_FACTS, USE_CASE_NAME, build_shared_rules

# 3 test transactions
for fact in SHARED_FACTS:
    print(fact["fact_id"])  # txn-001, txn-002, txn-003

# 3 payment-risk rules
rules = build_shared_rules()

# 8-condition nested DSL
dsl = complex_risk_condition()
```

This shared context lets you focus on learning features without context-switching between problem domains.

---

## Next Steps

- **[Quickstart](quickstart.md)** — 5-minute working example
- **[Conditions](conditions.md)** — Operator reference
- **[Complex Conditions](complex-conditions.md)** — AND/OR/NOT logic
- **[Domains & Tags](domains-and-tags.md)** — Rule organization

