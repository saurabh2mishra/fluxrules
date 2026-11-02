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
    conditions={
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

- `id`: Auto-generated unique identifier (or manual override)

- `name`: Human-readable rule name

- `domain`: Logical grouping (e.g., "fraud_detection", "compliance")

- `tags`: String set for filtering and categorization

- `conditions`: Nested tree defining when the rule fires

- `action`: What to do when the rule matches

- `priority`: Execution order (higher = runs first). All matching rules fire; priority only orders them. Ties are currently broken by rule ID (highest first), which is not a guaranteed contract, so use distinct priorities if order matters. Same-group, same-priority rules raise a validation warning.

**See:** [examples/18_unified_rule.py](https://github.com/saurabh2mishra/fluxrules/blob/main/examples/18_unified_rule.py)

---

## Engine

An **Engine** evaluates facts against loaded rules and returns matched rules and actions.

**Source:** `src/fluxrules/engine/` (interfaces and implementations)

A single engine is available:

- **PhreakEngine** (the only engine): Lazy, agenda-driven evaluation with stateless (default) and streaming modes

**Quick Example:**
```python
from fluxrules import PhreakEngine

engine = PhreakEngine()
engine.load_rules([rule])

fact = {"amount": 6000, "country": "NG"}
result = engine.evaluate(fact)
```

The engine has two evaluation modes, stateless and streaming.
[The PHREAK Engine](engine-comparison.md) explains how each mode works, and
[Choosing an Evaluation Mode](choosing-an-engine.md) helps you pick one.

---

## Fact

A **Fact** is the data you check against your rules, such as one payment. It
is a flat dictionary of field names and values:

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

A rule refers to a field by its key, as in `F("amount") > 1000`.

Facts often arrive in other shapes, and FluxRules handles each of them:

- **Nested data**, such as `{"payment": {"amount": 4200}}`. The engine reads
  flat keys only, so flatten it first. The nested value then becomes the
  dotted key `"payment.amount"`. See [Nested Facts](nested-facts.md).
- **Typed models**, such as a Pydantic model or a dataclass. The engine turns
  them into a flat dictionary for you. See [Typed Facts](typed-facts.md).
- **Raw input** that needs cleaning, renaming or enriching. A fact pipeline
  prepares it before evaluation. See [Fact Pipeline](fact-pipeline.md).

Each `engine.evaluate(fact)` call is independent by default: the engine keeps
nothing from one call to the next. Streaming mode and sessions keep state on
purpose, and you opt into each.

To follow a single fact from the moment it arrives to the actions it
produces, read [From Fact to Action](fact-to-action.md). To choose how your
application sends facts to the engine (one at a time, in batches, as a stream,
from the command line or over HTTP), read
[Ways to Evaluate a Fact](evaluating-facts.md).

---

## Conditions

A **condition tree** is a nested tree that defines when a rule fires. It combines:

- Simple conditions (field comparisons)

- Logical operators (AND, OR, NOT)

- Nested groups

**Basic condition:**
```python
from fluxrules import F

F("amount") > 5000
```

**Nested conditions (with AND/OR):** `&` means both must be true, `|` means either one is enough.
```python
from fluxrules import F

(F("amount") > 5000) & (F("country").isin(["NG", "SN"]))
```

**With NOT:** `~` means the condition must be false.
```python
from fluxrules import F

~F("email_domain").ends_with("trusted.com")
```

Every expression is stored as a plain dictionary tree, the same format YAML files
and the HTTP API use. The AND example above is stored as:

```python
{
    "type": "group",
    "op": "AND",
    "children": [
        {"type": "condition", "field": "amount", "op": ">", "value": 5000},
        {"type": "condition", "field": "country", "op": "in", "value": ["NG", "SN"]},
    ],
}
```

You can write the dictionary by hand when you prefer. See
[Authoring Rules](authoring-rules.md) for all the ways to write a condition.

**Validation:** Use `from fluxrules.domain.conditions.validation import validate_conditions`

**See:** [examples/02_complex_conditions.py](https://github.com/saurabh2mishra/fluxrules/blob/main/examples/02_complex_conditions.py), [examples/13_complex_rules.py](https://github.com/saurabh2mishra/fluxrules/blob/main/examples/13_complex_rules.py)

---

## Evaluation Result

When you evaluate a fact, the engine returns a result object with:

```python
result = engine.evaluate(fact)

# result.fired_rules: list of rule IDs that matched
# result.actions: list of actions to execute
# result.latency_ms: execution time in milliseconds
```

**Example:**
```python
print(f"Matched: {result.fired_rules}")  # [1001, 1003]
print(f"Actions: {result.actions}")       # ['manual_review', 'block_payment']
print(f"Time: {result.latency_ms}ms")     # 1.2ms
```

The engine does not run the actions itself. It returns their names, and your
application decides what to do with them. [Actions](custom-actions.md) shows
how to register a handler for each action name.

**See:** [examples/15_action_system.py](https://github.com/saurabh2mishra/fluxrules/blob/main/examples/15_action_system.py)

---

## Domain

A **Domain** is a logical grouping of rules. Rules with the same domain typically handle a specific problem area. 

For example depending on how your rules are grouped you can give a name e.g. `compliance` or `fraud_detections` etc.


**Filtering by domain:**
```python
from fluxrules import F, PhreakEngine, Rule

# Define rules with domains
rule1 = Rule(name="rule1", domain="fraud_detection", conditions=F("amount") > 5000, action="flag")
rule2 = Rule(name="rule2", domain="compliance", conditions=F("country") == "NG", action="review")
rule3 = Rule(name="rule3", domain="fraud_detection", conditions=F("type") == "transaction", action="process")

all_rules = [rule1, rule2, rule3]

# Load only fraud_detection rules
fraud_rules = [r for r in all_rules if r.domain == "fraud_detection"]

engine = PhreakEngine()
engine.load_rules(fraud_rules)
```

**See:** [examples/03_domains_and_tags.py](https://github.com/saurabh2mishra/fluxrules/blob/main/examples/03_domains_and_tags.py)

---

## Tag

A **Tag** is a string label for categorization and filtering.

**Filtering by tag:**
```python
# Get all tier_0 rules
tier0_rules = [r for r in all_rules if "tier_0" in (r.tags or set())]
```

**See:** [examples/03_domains_and_tags.py](https://github.com/saurabh2mishra/fluxrules/blob/main/examples/03_domains_and_tags.py)

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

# 8-condition nested tree
dsl = complex_risk_condition()
```

This shared context lets you focus on learning features without context-switching between problem domains.

---

## Next Steps

- **[From Fact to Action](fact-to-action.md)**: one fact, followed through every stage
- **[Ways to Evaluate a Fact](evaluating-facts.md)**: every way to send facts to the engine
- **[Authoring Rules](authoring-rules.md)**: the ways to write a rule
- **[Conditions](conditions.md)**: operator reference

