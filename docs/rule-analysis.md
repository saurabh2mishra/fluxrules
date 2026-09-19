# Rule Analysis

**Prerequisites:** [Concepts](concepts.md) (Rule).

---

Analyze rules for coverage, conflicts, and dead rules.

## Rule coverage

Check which rules are actually firing:

```python
from fluxrules import Rule
from fluxrules.engine.phreak import PhreakEngine

rule1 = Rule(name="rule1", condition_dsl={"type": "condition", "field": "status", "op": "==", "value": "active"}, action="allow")
rule2 = Rule(name="rule2", condition_dsl={"type": "condition", "field": "amount", "op": ">", "value": 5000}, action="flag")
rules = [rule1, rule2]

engine = PhreakEngine()
engine.load_rules(rules)

# Track rule matches across facts
coverage = {}
facts = [{"status": "active", "amount": 3000}, {"status": "active", "amount": 6000}]
for fact in facts:
    result = engine.evaluate(fact)
    for rule_id in result.fired_rules:
        coverage[rule_id] = coverage.get(rule_id, 0) + 1

# Find unused rules
all_rule_ids = set(r.name for r in rules)
covered_ids = set(coverage.keys())
unused = all_rule_ids - covered_ids
print(f"Unused rules: {unused}")
```

print(f"Unused rules: {unused}")
```

## Conflict detection

Rules may fire for the same fact:

```python
result = engine.evaluate(fact)

if len(result.fired_rules) > 1:
    print(f"Multiple rules matched: {result.fired_rules}")
    # May indicate conflicting logic
```

## Dead rule detection

Rules that never fire under any condition:

```python
from fluxrules import Rule
from fluxrules.engine.phreak import PhreakEngine

# Setup rules and engine
rules = [
    Rule(name="rule1", condition_dsl={"type": "condition", "field": "status", "op": "==", "value": "active"}, action="allow"),
    Rule(name="rule2", condition_dsl={"type": "condition", "field": "amount", "op": ">", "value": 5000}, action="flag"),
]
engine = PhreakEngine()
engine.load_rules(rules)

# Evaluate against diverse fact set
comprehensive_facts = [
    {"status": "active", "amount": 3000},
    {"status": "inactive", "amount": 6000},
    {"status": "active", "amount": 10000},
]

coverage = {}
for fact in comprehensive_facts:
    result = engine.evaluate(fact)
    for rule_id in result.fired_rules:
        coverage[rule_id] = True

# Dead rules
all_ids = set(r.name for r in rules)
dead = [r for r in rules if r.name not in coverage]

print(f"Dead rules: {[r.name for r in dead]}")
```

---

## Next Steps

- **Concepts** — See [Concepts](concepts.md) for rule fundamentals
- **Rule Lifecycle** — See [Rule Lifecycle](rule-lifecycle.md) for rule management
