# Action Registry

**Prerequisites:** [Custom Actions](custom-actions.md).

---

Advanced patterns for registering and managing custom actions.

## Basic registry operations

```python python skip
from fluxrules.plugins.actions import action_registry

# List all registered actions
all_actions = action_registry.list_actions()
print(f"Registered actions: {all_actions}")

# Filter actions by category
notifications = action_registry.get_actions_by_category("notifications")
```

## Action metadata

Every registered action exposes metadata:

```python python skip
from fluxrules.plugins.actions import action_registry, action

@action(
    name="send_alert",
    description="Send alert to monitoring system",
    category="alerts"
)
def send_alert(**kwargs):
    return {"sent": True}

# Access metadata (after registration)
all_actions = action_registry.list_actions()
print(f"Registered actions: {all_actions}")
```

## Execution patterns

### Direct execution

```python python skip
# Demonstration of action registry API
# result = action_registry.execute(
#     "send_alert",
#     severity="high",
#     message="Fraud detected"
# )
```

### Batch execution

```python python skip
# Batch execution of actions
# actions = ["send_alert", "log_event", "notify_team"]
# for action_name in actions:
#     result = action_registry.execute(action_name, **kwargs)
```

### Async execution

```python
import asyncio

async def run_async_action():
    result = await action_registry.execute_async(
        "log_to_database",
        event_id="123",
        data={...}
    )
    return result
```

## Action categories

Organize related actions with categories:

```python
# Notifications
@action(name="send_email", category="notifications")
def send_email(**kwargs): ...

@action(name="send_slack", category="notifications")
def send_slack(**kwargs): ...

# Logging
@action(name="log_event", category="logging")
def log_event(**kwargs): ...

# Filtering actions by category
notifications = action_registry.get_actions_by_category("notifications")
```

---

## Next Steps

- **Custom Actions** — See [Custom Actions](custom-actions.md) for @action decorator
- **Example** — See [Example 21: Action Registry](https://github.com/fluxrules/fluxrules/blob/main/examples/21_action_registry.py)
