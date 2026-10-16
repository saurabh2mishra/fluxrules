# Sessions

**Prerequisites:** [Working Memory](working-memory.md) (fact accumulation) and [Concepts](concepts.md) (Rule, Engine).

---

Sessions provide stateful, multi-step evaluation with snapshot support. Use sessions when you need to:

1. **Accumulate facts** across multiple steps
2. **Save/restore state** for recovery
3. **Isolate rule evaluation** in separate execution contexts

## Creating and using a session

Create a session via `RuleService`, then accumulate facts and evaluate:

```python
# python skip
from fluxrules import Rule
from fluxrules.domain.models import Ruleset
from fluxrules.services.rule_service import RuleService

service = RuleService.create()

# Build rules and register them as a named ruleset
rules = [
    Rule(
        name="verify_kyc",
        conditions={"type": "condition", "field": "kyc_status", "op": "==", "value": "verified"},
        action="proceed_to_payment",
    ),
    Rule(
        name="check_amount",
        conditions={"type": "condition", "field": "amount", "op": ">", "value": 10000},
        action="require_approval",
    ),
]
ruleset = Ruleset(
    group="order_rules",
    rules=tuple(r.to_engine_rule(group="order_rules") for r in rules),
)
service.persist(ruleset)

# Create a session bound to that ruleset and accumulate facts
session = service.create_session("order_rules")
session.add_fact("kyc_status", "verified")
session.add_fact("amount", 15000)
result = session.evaluate()
print(f"Actions: {result.actions}")  # actions whose rules matched
```

**Key point:** Sessions accumulate facts. You evaluate once against all accumulated facts, not after each `add_fact()`.

## Session lifecycle

A session has these phases:

1. **Create** - `service.create_session(ruleset_id)` initializes an empty session bound to that ruleset
2. **Accumulate** - `add_fact()`, `add_facts()`, `remove_fact()`, `clear_facts()`
3. **Evaluate** - `evaluate()` matches rules against accumulated facts
4. **Save** - `save()` exports to JSON snapshot
5. **Restore** - `EvaluationSession.restore(json, service)` reconstructs from snapshot

Evaluations are **independent** - each `evaluate()` is stateless. The session remembers facts but not evaluation history.

```python
# python skip
# Multiple evaluations with different facts (demonstration)
# session.add_fact("risk_score", 50)
# result1 = session.evaluate()
#
# session.remove_fact("risk_score")
# session.add_fact("risk_score", 80)
# result2 = session.evaluate()  # Different result due to updated fact
```

## Snapshot: save and restore

Serialize a session to JSON for checkpointing or recovery:

```python
# python skip
# Checkpoint current state
snapshot = session.save()  # Returns JSON string

# Later: restore in a new process/thread
restored = EvaluationSession.restore(snapshot, service)
result = restored.evaluate()

# The restored session has the same facts and metadata
print(restored.facts)  # Same as original session
```

Snapshots include:
- **execution_id** - unique session identifier
- **facts** - all accumulated fact key-value pairs
- **timestamp** - when the snapshot was created
- **metadata** - optional custom data (application-specific)

Use snapshots to:
- **Pause workflows** - save after step 1, restore in step 2
- **Recover failures** - restart from a known state
- **Audit trail** - keep JSON copies of evaluation context

## Isolation

Each session is isolated. Facts in one session do not affect another:

```python
# python skip
# Each session is independent — same ruleset, different fact sets
session1 = service.create_session("order_rules")
session1.add_fact("user_type", "premium")

session2 = service.create_session("order_rules")
session2.add_fact("user_type", "basic")

result1 = session1.evaluate()  # Evaluates with "premium"
result2 = session2.evaluate()  # Evaluates with "basic"
# No cross-contamination
```

Use sessions to evaluate the same ruleset independently for different users, transactions, or workflows.

---

## Next Steps

- **Working Memory** - See [Working Memory](working-memory.md) for fact store details
- **Example** - See [Example 12: API Usage](https://github.com/saurabh2mishra/fluxrules/blob/main/examples/12_api_usage.py) for session patterns in HTTP services
- **Persistence** - See [Persistence](persistence.md) for database integration
