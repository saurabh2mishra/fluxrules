# Working Memory and State

**Prerequisites:** [Concepts](concepts.md) (Rule, Engine, Fact) and [Conditions](conditions.md) (DSL format).

---

FluxRules evaluates fact maps against rules. This page describes:

1. **Single-fact evaluation** - how engines match one fact at a time
2. **Working memory** - how to store and retrieve facts
3. **Stateful sessions** - how to accumulate facts across multiple evaluations

Each engine evaluates independently. If you need multi-fact correlation, see [Cross-Fact Rules](cross-fact-rules.md).

## Single-fact evaluation

`PhreakEngine` evaluates one fact dict per call:

```python
from fluxrules import Rule
from fluxrules.engine.phreak import PhreakEngine

rule = Rule(
    name="high_value_flag",
    condition_dsl={"type": "condition", "field": "amount", "op": ">", "value": 5000},
    action="flag_for_review",
    persist=False,
)

engine = PhreakEngine()
engine.load_rules([rule])

# Evaluate a single fact
result = engine.evaluate({"amount": 7500})
print(f"Matched rules: {result.fired_rules}")  # [1]
```

Each call to `evaluate()` is independent-engines do not correlate facts across time or aggregate over collections. Pass pre-aggregated facts to the engine.

---

## Working memory (fact store)

Every engine has a built-in fact store accessed via `assert_fact` and `retract_fact`:

```python
from fluxrules import Rule
from fluxrules.engine.phreak import PhreakEngine

engine = PhreakEngine()
engine.load_rules([
    Rule(name="test", condition_dsl={"type": "condition", "field": "x", "op": ">", "value": 10}, action="act", persist=False)
])

# Assert facts into the store
fact_id_1 = engine.assert_fact({"x": 15})  # Returns a fact ID
fact_id_2 = engine.assert_fact({"x": 5})

# Retrieve fact_id_1 - still in working memory
# But evaluate() does not automatically use stored facts
result = engine.evaluate({"x": 20})
print(f"Matched: {result.fired_rules}")  # [1] (matches the evaluate() call, not stored facts)

# Remove a fact from storage
engine.retract_fact(fact_id_1)
```

**Key insight:** `assert_fact` and `retract_fact` manage storage only. They do *not* trigger rule matching. Use `evaluate()` to match facts against rules.

---

## Stateful sessions

For workflows that accumulate facts across multiple steps, use `EvaluationSession`:

```python
from fluxrules import Rule
from fluxrules.services.rule_service import RuleService

# Create a ruleset (persisted rules)
service = RuleService.create()
rules = [
    Rule(
        name="kyc_verified",
        domain="compliance",
        condition_dsl={"type": "condition", "field": "kyc_status", "op": "==", "value": "verified"},
        action="proceed",
        persist=True,
    ),
    Rule(
        name="high_risk",
        domain="fraud",
        condition_dsl={"type": "condition", "field": "amount", "op": ">", "value": 10000},
        action="review",
        persist=True,
    ),
]

# Accumulate facts and evaluate (python skip for demo)
# from fluxrules.engine.phreak import PhreakEngine
#
# engine = PhreakEngine()
# engine.load_rules(rules)
#
# # Evaluate with accumulated facts
# facts = {"kyc_status": "verified", "amount": 15000}
#
# # Evaluate against all facts
# result = engine.evaluate(facts)
print(f"Matched: {result.fired_rules}")  # Both rules match
```

**Session methods:**

- `add_fact(key, value)` - set or update one field
- `add_facts(dict)` - merge multiple fields
- `remove_fact(key)` - remove one field (no error if missing)
- `clear_facts()` - remove all facts
- `evaluate()` - evaluate ruleset against accumulated facts

---

## Snapshot save and restore

Sessions can be serialized to JSON snapshots for recovery:

```python
# python skip
# Save session to JSON (demonstration - requires session object)
# snapshot_json = session.save()

# Later: restore the session
# restored_session = type(session).restore(snapshot_json, service)
# result = restored_session.evaluate()
```

The snapshot includes facts, session ID, timestamp, and optional metadata. Use this to checkpoint multi-step workflows.

---

## Next Steps

- **Multi-fact correlation** - See [Cross-Fact Rules](cross-fact-rules.md) for the `CrossFactEngine`
- **Sessions in production** - See [Sessions](sessions.md) for session lifecycle and lifecycle management
- **Streaming mode** - See example [23_streaming_vs_stateless.py](https://github.com/fluxrules/fluxrules/blob/main/examples/23_streaming_vs_stateless.py) for delta behavior
