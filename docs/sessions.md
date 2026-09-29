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
from fluxrules.services.rule_service import RuleService

# Create service and add rules (demonstration - requires service layer setup)
service = RuleService.create()
rules = [
    Rule(
        name="verify_kyc",
        condition_dsl={"type": "condition", "field": "kyc_status", "op": "==", "value": "verified"},
        action="proceed_to_payment",
    ),
    Rule(
        name="check_amount",
        condition_dsl={"type": "condition", "field": "amount", "op": ">", "value": 10000},
        action="require_approval",
    ),
]

# For stateful workflows, use sessions:
# session = service.create_session()
# session.add_fact("kyc_status", "verified")
# session.add_fact("amount", 15000)
# result = session.evaluate()
# print(f"Actions: {result.actions}")  # ["proceed_to_payment", "require_approval"]
```

**Key point:** Sessions accumulate facts. You evaluate once against all accumulated facts, not after each `add_fact()`.

## Session lifecycle

A session has these phases:

1. **Create** — `service.create_session()` initializes an empty session
2. **Accumulate** — `add_fact()`, `add_facts()`, `remove_fact()`, `clear_facts()`
3. **Evaluate** — `evaluate()` matches rules against accumulated facts
4. **Save** — `save()` exports to JSON snapshot
5. **Restore** — `EvaluationSession.restore(json, service)` reconstructs from snapshot

Evaluations are **independent** — each `evaluate()` is stateless. The session remembers facts but not evaluation history.

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
# Checkpoint current state (demonstration - requires session object)
# snapshot = session.save()  # Returns JSON string
#
# Later: restore in a new process/thread
# restored = type(session).restore(snapshot, service)
# result = restored.evaluate()
#
# The restored session has the same facts and metadata
print(restored.facts)  # Same as original session
```

Snapshots include:
- **execution_id** — unique session identifier
- **facts** — all accumulated fact key-value pairs
- **timestamp** — when the snapshot was created
- **metadata** — optional custom data (application-specific)

Use snapshots to:
- **Pause workflows** — save after step 1, restore in step 2
- **Recover failures** — restart from a known state
- **Audit trail** — keep JSON copies of evaluation context

## Isolation

Each session is isolated. Facts in one session do not affect another:

```python
# python skip
# Session isolation demonstration (requires service setup)
# session1 = service.create_session()
# session1.add_fact("user_type", "premium")
#
# session2 = service.create_session()
# session2.add_fact("user_type", "basic")
#
# result1 = session1.evaluate()  # Evaluates with "premium"
# result2 = session2.evaluate()  # Evaluates with "basic"
# # No cross-contamination
```

Use sessions to evaluate the same ruleset independently for different users, transactions, or workflows.

---

## Next Steps

- **Working Memory** — See [Working Memory](working-memory.md) for fact store details
- **Example** — See [Example 12: API Usage](https://github.com/fluxrules/fluxrules/blob/main/examples/12_api_usage.py) for session patterns in HTTP services
- **Persistence** — See [Persistence](persistence.md) for database integration
