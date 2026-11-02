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
from fluxrules import F, Rule
from fluxrules.domain.models import Ruleset
from fluxrules.services.rule_service import RuleService

service = RuleService.create()

# Build rules and register them as a named ruleset
rules = [
    Rule(
        id=1,
        name="verify_kyc",
        conditions=F("kyc_status") == "verified",
        action="proceed_to_payment",
    ),
    Rule(
        id=2,
        name="check_amount",
        conditions=F("amount") > 10000,
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
assert sorted(result.fired_rules) == [1, 2]
```

**Key point:** Sessions accumulate facts. You evaluate once against all accumulated facts, not after each `add_fact()`.

## Session lifecycle

A session has these phases:

1. **Create**: `service.create_session(ruleset_id)` initializes an empty session bound to that ruleset
2. **Accumulate**: `add_fact()`, `add_facts()`, `remove_fact()`, `clear_facts()`
3. **Evaluate**: `evaluate()` matches rules against accumulated facts
4. **Save**: `save()` exports to JSON snapshot
5. **Restore**: `EvaluationSession.restore(json, service)` reconstructs from snapshot

Evaluations are **independent**: each `evaluate()` is stateless. The session remembers facts but not evaluation history.

```python
# Multiple evaluations with different facts
session.add_fact("amount", 500)
result1 = session.evaluate()
assert result1.fired_rules == [1]  # only the KYC rule

session.add_fact("amount", 50000)  # add_fact replaces the old value
result2 = session.evaluate()
assert sorted(result2.fired_rules) == [1, 2]  # different result due to the updated fact
```

## Snapshot: save and restore

Serialize a session to JSON for checkpointing or recovery:

```python
from fluxrules.services.session import EvaluationSession

# Checkpoint current state
snapshot = session.save()  # Returns JSON string

# Later: restore in a new process/thread
restored = EvaluationSession.restore(snapshot, service)
result = restored.evaluate()

# The restored session has the same facts and metadata
print(restored.facts)  # Same as original session
assert restored.facts == session.facts
```

Snapshots include:
- **execution_id**: unique session identifier
- **facts**: all accumulated fact key-value pairs
- **timestamp**: when the snapshot was created
- **metadata**: optional custom data (application-specific)

Use snapshots to:
- **Pause workflows**: save after step 1, restore in step 2
- **Recover failures**: restart from a known state
- **Audit trail**: keep JSON copies of evaluation context

## Isolation

Each session is isolated. Facts in one session do not affect another:

```python
# Each session is independent: same ruleset, different fact sets
session1 = service.create_session("order_rules")
session1.add_fact("amount", 20000)

session2 = service.create_session("order_rules")
session2.add_fact("amount", 100)

result1 = session1.evaluate()  # Evaluates with 20000
result2 = session2.evaluate()  # Evaluates with 100
# No cross-contamination
assert (result1.fired_rules, result2.fired_rules) == ([2], [])
```

Use sessions to evaluate the same ruleset independently for different users, transactions, or workflows.

## Sessions over HTTP

The HTTP API has its own sessions, under `/api/v1/sessions`. They work
differently from the Python sessions on this page:

- **Python session**: each `add_fact(key, value)` adds one field to a single
  fact, and `evaluate()` checks that one fact.
- **HTTP session**: each `POST /api/v1/sessions/{id}/facts` stores a whole
  fact under a `fact_id`, and `POST /api/v1/sessions/{id}/evaluate` evaluates
  every stored fact on its own, returning one result per fact.

See [HTTP API Reference: Sessions](rest-api.md#sessions).

---

## Next Steps

- **Working Memory**: See [Working Memory](working-memory.md) for fact store details
- **Example**: See [Example 12: API Usage](https://github.com/saurabh2mishra/fluxrules/blob/main/examples/12_api_usage.py) for session patterns in HTTP services
- **Persistence**: See [Persistence](persistence.md) for database integration
