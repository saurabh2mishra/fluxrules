# Rule Lifecycle

**Prerequisites:** [Concepts](concepts.md) (Rule) and [Persistence](persistence.md) (database).

---

A rule's lifecycle consists of: **Create** → **Load** → **Validate** → **Evaluate** → **Delete**.

## Create a rule

```python
from fluxrules import F, Rule
from fluxrules.engine.phreak import PhreakEngine

rule = Rule(
    name="high_value_transaction",
    domain="fraud_detection",
    tags=frozenset(["tier_1", "manual_review"]),
    conditions=F("amount") > 5000,
    action="require_approval",
    priority=10,
    persist=True,  # Enable database persistence
)

print(f"Rule created: {rule.name} (ID: {rule.id})")
```

**Core Rule fields:**

| Field | Type | Required | Purpose |
|-------|------|----------|---------|
| `name` | `str` | Yes | Descriptive rule name |
| `domain` | `str` | No | Logical grouping (default: "default") |
| `tags` | `frozenset[str]` | No | Searchable keywords |
| `conditions` | `dict` | Yes | Rule logic (condition tree format) |
| `action` | `str \| tuple[str, ...]` | No | Action when rule fires |
| `priority` | `int` | No | Evaluation priority (higher first) |
| `persist` | `bool` | No | Store in database (default: False) |

## Load rules

### From Python code (temporary)

```python
from fluxrules import F, Rule

rules = [
    Rule(
        name="rule1",
        conditions=F("amount") > 1000,
        action="act1",
        persist=False,
    ),
    Rule(
        name="rule2",
        conditions=F("country") == "US",
        action="act2",
        persist=False,
    ),
]

engine = PhreakEngine()
engine.load_rules(rules)
```

### From database (persistent)

```python
# python skip
from fluxrules.services.rule_service import RuleService

service = RuleService.create()
loaded_rules = service.load_ruleset(ruleset_id=1)
```

### From YAML file

```python
# python skip
from fluxrules.adapters.loaders import load_rules_from_yaml

rules_dicts = load_rules_from_yaml("rules.yaml")
rules = [Rule(**r) for r in rules_dicts]
```

## Validate a rule

```python
from fluxrules import F
from fluxrules.domain.conditions.validation import validate_conditions, ConditionValidationError

# Validate condition tree syntax before creating a rule
dsl = (F("amount") > 5000).to_dict()

try:
    validate_conditions(dsl)
    print("✓ Conditions are valid")
except ConditionValidationError as e:
    print(f"✗ Invalid conditions: {e}")
```

Invalid DSLs raise `ConditionValidationError`. See [Validation Framework](validation-framework.md) for details.

## Evaluate rules

```python
from fluxrules.engine.phreak import PhreakEngine

engine = PhreakEngine()
engine.load_rules(rules)

# Single evaluation
result = engine.evaluate({"amount": 7500, "country": "US"})
print(f"Matched: {result.fired_rules}")
print(f"Actions: {result.actions}")

# Multiple evaluations
facts_list = [{"amount": 7500, "country": "US"}, {"amount": 100, "country": "CA"}]
for fact in facts_list:
    result = engine.evaluate(fact)
    # Process result...
```

## Delete a rule

### From database

```python
# python skip
from fluxrules.services.rule_service import RuleService

service = RuleService.create()
service.delete_rule(rule_id=1)
```

Deleted rules are removed from the database. In-memory rules loaded via `engine.load_rules()` must be reloaded.

### From memory

In-memory rules (rules loaded via code, not persisted) cannot be deleted after loading. Create a new engine instance and reload without the unwanted rule:

```python
# Original engine
engine.load_rules(rules)

# Create a new engine with only the first rule
new_engine = PhreakEngine()
new_engine.load_rules([rules[0]])
```

## Rule state

Rules are **immutable** once created. To change a rule, create a new Rule with the updated fields:

```python
# python skip
# Original rule
from fluxrules import F

old_rule = Rule(
    name="check_amount",
    conditions=F("amount") > 1000,
    action="flag",
    persist=True,
)

# Updated rule (new instance)
new_rule = Rule(
    name="check_amount",
    conditions=F("amount") > 5000,
    action="flag",
    persist=True,
)

# Delete old, persist new
service.delete_rule(old_rule.id)
service.persist(Ruleset(group="default", rules=(new_rule.to_engine_rule(),)))
```

---

## Next Steps

- **Validation** - See [Validation Framework](validation-framework.md) for condition validation
- **Complex Conditions** - See [Complex Conditions](complex-conditions.md) for AND/OR/NOT logic
- **Persistence** - See [Persistence](persistence.md) for database management
- **Custom Actions** - See [Custom Actions](custom-actions.md) for action handlers
