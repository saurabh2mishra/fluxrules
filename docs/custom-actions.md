# Custom Actions

**Prerequisites:** [Concepts](concepts.md) (Rule, action field) and [Validation Framework](validation-framework.md).

---

Actions are strings or tuples of strings that are executed when a rule fires. FluxRules supports:

1. **String actions** - Simple action names from your application
2. **Action registry** - Register custom handlers with the `@action` decorator
3. **Built-in actions** - Default actions like `flag` and `alert`

## Using actions in rules

```python
from fluxrules import Rule
from fluxrules.engine.phreak import PhreakEngine

rule1 = Rule(
    name="check_high_value",
    condition_dsl={"type": "condition", "field": "amount", "op": ">", "value": 5000},
    action="require_approval",  # Single action (string)
    persist=False,
)

rule2 = Rule(
    name="check_fraud",
    condition_dsl={"type": "condition", "field": "ip_risk_score", "op": ">", "value": 80},
    actions=("block", "notify_security"),  # Multiple actions (tuple)
    persist=False,
)

engine = PhreakEngine()
engine.load_rules([rule1, rule2])

result = engine.evaluate({"amount": 7500, "ip_risk_score": 90})
print(f"Actions: {result.actions}")  # ["require_approval"] + ["block", "notify_security"]
```

## Built-in actions

- **`flag`** - Mark fact for manual review
- **`alert`** - Send alert notification
- **`skip`** - Skip further evaluation
- Custom strings - Any string your application recognizes

## Register custom action handlers

Use the `@action` decorator to register a handler that executes when an action fires:

```python
from fluxrules.plugins.actions import action
from fluxrules.plugins.actions import action_registry


# Register a simple action
@action(
    name="send_approval_request",
    description="Send approval request to team",
    category="notifications",
)
def send_approval_request(transaction_id: str, amount: int) -> dict:
    """Execute when 'send_approval_request' action fires."""

    # Your implementation: call API, send email, etc.
    print(f"Sending approval request for txn {transaction_id} ({amount})")

    return {"success": True, "action": "send_approval_request", "transaction_id": transaction_id}


# Register an async action
@action(
    name="log_to_database",
    description="Log event to database",
    category="logging",
    async_handler=True,
)
async def log_to_database(event_id: str) -> dict:
    """Async action handler."""

    # Your async implementation
    return {"logged": True, "event_id": event_id}


# List all registered actions
print(action_registry.list_actions())

# Execute an action programmatically
result = action_registry.execute("send_approval_request", transaction_id="TXN-123", amount=7500)
```

## Action metadata

Inspect registered actions:

```python
from fluxrules.plugins.actions import action_registry

# Get action metadata
info = action_registry.get("send_approval_request")
print(f"Name: {info.name}")
print(f"Description: {info.description}")
print(f"Category: {info.category}")

# Get actions by category
notification_actions = action_registry.get_actions_by_category("notifications")

# Get action signature (parameters)
sig = action_registry.get_action_signature("send_approval_request")
```

## Action execution in evaluations

When a rule fires, its actions are included in the evaluation result:

```python
fact = {"amount": 7500, "ip_risk_score": 90}
result = engine.evaluate(fact)

# result.actions is a list of action names that fired
for action_name in result.actions:
    print(f"Execute: {action_name}")
    
    # Execute registered handler (if defined)
    try:
        handler_result = action_registry.execute(action_name, **fact)
        print(f"  Result: {handler_result}")
    except ValueError:
        # Action not registered - your app handles the string
        print(f"  (Application handles '{action_name}')")
```

## Common patterns

### Fire multiple actions

```python
Rule(
    name="suspicious_transaction",
    condition_dsl={"type": "condition", "field": "amount", "op": ">", "value": 50000},
    actions=("block", "notify_fraud_team", "log_to_database"),
    persist=False,
)
```

### Context-aware actions

```python
@action(name="escalate_if_high_value", description="Escalate high-value transactions")
def escalate_if_high_value(**kwargs) -> dict:
    amount = kwargs.get("amount", 0)
    
    if amount > 50000:
        level = "executive"
    elif amount > 10000:
        level = "manager"
    else:
        level = "standard"
    
    return {"escalated_to": level, "amount": amount}
```

### Chain actions

```python
@action(name="notify_then_block")
def notify_then_block(**kwargs) -> dict:
    """Notify first, then block."""
    action_registry.execute("notify_fraud_team", **kwargs)
    action_registry.execute("block_transaction", **kwargs)
    return {"action": "notify_then_block", "status": "complete"}
```

---

## Next Steps

- **Rule Lifecycle** - See [Rule Lifecycle](rule-lifecycle.md) for rule creation and deletion
- **Example** - See [Example 15: Action System](https://github.com/saurabh2mishra/fluxrules/blob/main/examples/15_action_system.py) for working code
- **Action Registry** - See [Action Registry](action-registry.md) for advanced registration patterns
