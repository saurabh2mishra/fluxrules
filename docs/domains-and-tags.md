# Domains and Tags

Organize and filter rules using domains (logical grouping) and tags (multi-dimensional labeling).

**Prerequisites:** Familiarity with [Rules](concepts.md) and rule creation (see [Getting Started](quickstart.md)).

---

## Overview

As your rule systems grow, you need ways to:
- Organize rules by business area (fraud, compliance, marketing)
- Filter rules at evaluation time (only evaluate tier_1 rules)
- Manage rules by team or feature
- Query rules without loading everything

**Domains** and **tags** enable this organization:

- **Domain**: Single category each rule belongs to (mutually exclusive)
- **Tags**: Multiple labels per rule (cross-cutting concerns)

---

## Domains

A domain is a logical grouping. Each rule belongs to exactly one domain.

### Define a Domain

```python
from fluxrules.domain import Rule

rule = Rule(
    name="fraud_check",
    domain="fraud_detection",  # Single domain per rule
    condition_dsl={"type": "condition", "field": "amount", "op": ">", "value": 5000},
    action="flag_for_review"
)
```

Default domain is `"default"` if not specified:

```python
rule_no_domain = Rule(
    name="simple_rule",
    condition_dsl={"type": "condition", "field": "status", "op": "==", "value": "active"},
    action="process"
)
# rule_no_domain.domain == "default"
```

### Query by Domain

```python
from fluxrules import Rule
from fluxrules.engine.phreak import PhreakEngine

rules = [
    Rule(name="r1", domain="fraud_detection", condition_dsl={"type": "condition", "field": "status", "op": "==", "value": "active"}, action="flag"),
    Rule(name="r2", domain="compliance", condition_dsl={"type": "condition", "field": "country", "op": "==", "value": "US"}, action="block"),
    Rule(name="r3", domain="fraud_detection", condition_dsl={"type": "condition", "field": "amount", "op": ">", "value": 5000}, action="review"),
]

engine = PhreakEngine()
engine.load_rules(rules)

# Evaluate against a fact
fact = {"status": "active", "country": "US", "amount": 6000}
result = engine.evaluate(fact)
print(f"Fired rules: {result.fired_rules}")
```

---

## Tags

Tags are labels you add to rules for cross-cutting organization. A rule can have unlimited tags.

### Add Tags to a Rule

```python
from fluxrules.domain import Rule

rule = Rule(
    name="vip_fast_track",
    domain="marketing",
    tags=frozenset(["vip", "urgent", "auto_action"]),  # Multiple tags
    condition_dsl={"type": "condition", "field": "customer_tier", "op": "==", "value": "vip"},
    action="fast_track_checkout"
)
```

Tags must be passed as `frozenset[str]`. Rule automatically converts lists to frozensets:

```python
# python skip
# Both work:
# Rule(name="r1", condition_dsl={...}, tags=frozenset(["tag1", "tag2"]))
# Rule(name="r2", condition_dsl={...}, tags=["tag1", "tag2"])  # Converted to frozenset
```

### Query by Tags

```python
from fluxrules import Rule
from fluxrules.engine.phreak import PhreakEngine

rules = [
    Rule(name="r1", tags=frozenset(["urgent", "vip"]), condition_dsl={"type": "condition", "field": "priority", "op": "==", "value": "high"}, action="action1"),
    Rule(name="r2", tags=frozenset(["low_priority"]), condition_dsl={"type": "condition", "field": "priority", "op": "==", "value": "low"}, action="action2"),
    Rule(name="r3", tags=frozenset(["urgent"]), condition_dsl={"type": "condition", "field": "type", "op": "==", "value": "alert"}, action="action3"),
]

engine = PhreakEngine()
engine.load_rules(rules)

# Evaluate against a fact
fact = {"priority": "high", "type": "notification"}
result = engine.evaluate(fact)
print(f"Fired: {result.fired_rules}")
```
```

---

## Real Example: Shared Payment Risk Dataset

The shared payment-risk use case demonstrates domains and tags in action:

```python
from shared_use_case import build_shared_rules

rules = build_shared_rules()

# Rule 1: Fraud detection domain, tier_1 and manual_review tags
# Rule 2: Compliance domain, tier_2 and block tags
# Rule 3: Risk operations domain, tier_1 and step_up tags

for rule in rules:
    print(f"{rule.name}: domain={rule.domain}, tags={rule.tags}")
```

**Output:**
```
triage_for_manual_review: domain=fraud_detection, tags=frozenset({'tier_1', 'manual_review', 'cross_border'})
triage_for_hard_block: domain=compliance, tags=frozenset({'tier_2', 'block', 'geo_risk'})
triage_for_step_up_auth: domain=risk_ops, tags=frozenset({'tier_1', 'step_up', 'identity'})
```

See [Example 03: Domains and Tags](https://github.com/fluxrules/fluxrules/blob/main/examples/03_domains_and_tags.py) for complete working code.

---

## Filtering by Domain and Tags

### Evaluate Specific Domain Only

```python
# python skip
# Demonstration using shared dataset (run from examples/ directory)
from fluxrules.engine.phreak import PhreakEngine
from fluxrules.engine import EvaluationFilter
from shared_use_case import SHARED_FACTS, build_shared_rules

engine = PhreakEngine()
engine.load_rules(build_shared_rules())

# Evaluate only fraud_detection rules
for fact in SHARED_FACTS:
    result = engine.evaluate(
        fact,
        filters=EvaluationFilter(domains=frozenset(["fraud_detection"]))
    )
    print(f"Fraud rules: {result.fired_rules}")

# Evaluate only compliance rules
for fact in SHARED_FACTS:
    result = engine.evaluate(
        fact,
        filters=EvaluationFilter(domains=frozenset(["compliance"]))
    )
    print(f"Compliance rules: {result.fired_rules}")
```

### Evaluate Specific Tags Only

```python
# Evaluate only tier_1 priority rules
result = engine.evaluate(
    fact,
    filters=EvaluationFilter(tags=frozenset(["tier_1"]))
)

# Evaluate only rules with both "manual_review" and "cross_border" tags
result = engine.evaluate(
    fact,
    filters=EvaluationFilter(tags=frozenset(["manual_review", "cross_border"]))
)
```

---

## Best Practices

### 1. Use Clear Domain Names

Choose domain names that map to business areas:

```python
# Good: Clear business areas
domains = ["fraud_detection", "compliance", "marketing", "risk_ops"]

# Confusing: Too broad or vague
domains = ["rules", "checks", "business_logic"]
```

### 2. Use Consistent Tag Naming

Establish tag conventions within your organization:

```python
# Tag naming patterns:
# Priority: tier_0, tier_1, tier_2
# Action: auto_action, manual_review, informational
# Status: experimental, stable, deprecated
# Scope: vip, enterprise, new_customer

tags_good = frozenset(["tier_1", "auto_action", "stable"])
tags_confusing = frozenset(["high", "auto", "new"])
```

### 3. Document Tag Meanings

Create a tag reference for your team:

```python
TAG_MEANINGS = {
    "tier_0": "Highest priority, critical business logic",
    "tier_1": "High priority, reviewed and tested",
    "tier_2": "Standard priority, production ready",
    "auto_action": "Can execute automatically",
    "manual_review": "Results must be reviewed by human",
    "experimental": "Still being tested",
    "stable": "Production-ready, well-tested",
}
```

### 4. Combine Domains and Tags for Powerful Queries

```python
from fluxrules import Rule
from fluxrules.engine.phreak import PhreakEngine

# Create diverse set of rules
all_rules = [
    Rule(name="r1", domain="fraud_detection", tags=frozenset(["tier_1"]), condition_dsl={"type": "condition", "field": "amount", "op": ">", "value": 5000}, action="flag"),
    Rule(name="r2", domain="fraud_detection", tags=frozenset(["tier_2"]), condition_dsl={"type": "condition", "field": "country", "op": "==", "value": "NG"}, action="review"),
    Rule(name="r3", domain="compliance", tags=frozenset(["tier_1", "stable"]), condition_dsl={"type": "condition", "field": "type", "op": "==", "value": "transfer"}, action="log"),
]

# Get all tier_1 rules in fraud_detection domain
tier1_fraud = [
    r for r in all_rules
    if r.domain == "fraud_detection" and "tier_1" in r.tags
]

# Load and evaluate
engine = PhreakEngine()
engine.load_rules(tier1_fraud)
result = engine.evaluate({"amount": 6000, "country": "NG"})
print(f"Matched: {result.fired_rules}")
```

---

## Limitations

- **Domain mutations**: Rules cannot change domain after creation
- **Tag mutation**: Tags cannot be modified after creation
- **Query combinations**: Filters use OR for multiple tags/domains (all matching are evaluated)


## Next Steps

- **[Complex Conditions](complex-conditions.md)** - AND/OR/NOT boolean logic for rules
- **[Custom Actions](custom-actions.md)** - Execute custom code when rules match
- **[Examples 03](https://github.com/fluxrules/fluxrules/blob/main/examples/03_domains_and_tags.py)** - Working code example
