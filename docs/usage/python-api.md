# Python API

**Prerequisites:** [Quickstart](../quickstart.md), [Concepts](../concepts.md).

---

## Quick Evaluation

Use the engine directly for simple cases:

```python
from fluxrules import Rule
from fluxrules.engine.phreak import PhreakEngine

# Define rules
rule = Rule(
    name="high_value",
    condition_dsl={"type": "condition", "field": "amount", "op": ">", "value": 1000},
    action="flag"
)

engine = PhreakEngine()
engine.load_rules([rule])

# Evaluate
result = engine.evaluate({"amount": 2500})
print(f"Matched: {result.fired_rules}")      # [1]
print(f"Actions: {result.actions}")          # ["flag"]
print(f"Latency: {result.latency_ms} ms")    # ~2ms
```

## Validation

Validate rules before use:

```python
from fluxrules import Rule
from fluxrules.services.rule_service import RuleService

# Create a rule and service
rule = Rule(
    name="check",
    condition_dsl={"type": "condition", "field": "status", "op": "==", "value": "active"},
    action="proceed"
)

service = RuleService.create()
# Validation is automatic during evaluation
```

## Engines (Direct)

For more control, use engines directly:

```python
from fluxrules import Rule
from fluxrules.engine.phreak import PhreakEngine

rule1 = Rule(name="rule1", condition_dsl={"type": "condition", "field": "status", "op": "==", "value": "active"}, action="flag")
rule2 = Rule(name="rule2", condition_dsl={"type": "condition", "field": "amount", "op": ">", "value": 5000}, action="review")

engine = PhreakEngine()
engine.load_rules([rule1, rule2])

result = engine.evaluate({"amount": 2500})
```

## RuleService (Sessions & Persistence)

Use `RuleService` for stateful workflows:

```python python skip
from fluxrules.services.rule_service import RuleService

service = RuleService.create()

# Create session requires ruleset_id
# ruleset_id = service.save_ruleset(name="payment_rules", rules=rules)
# session = service.create_session(ruleset_id)

# Add facts and evaluate
# session.assert_fact({"customer_id": "c1", "amount": 5000})
# result = session.evaluate()
# print(f"Matched: {result.fired_rules}")
```

---

## Next Steps

- **Engines** — See [The FluxRules Engine](../engine-comparison.md)
- **Sessions** — See [Sessions](../sessions.md) for stateful workflows
- **API Reference** — See [Reference: Public API](../reference/public-api.md)
