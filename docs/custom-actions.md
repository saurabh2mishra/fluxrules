# Actions

**Prerequisites:** [Concepts](concepts.md) (Rule, Evaluation Result).

---

An **action** is the name of what should happen when a rule fires, such as
`"manual_review"` or `"block"`. The engine does not run actions. It returns
their names in `result.actions`, and your application decides what each name
means. This keeps rules free of side effects, so you can evaluate them in a
test, a dry run or a batch job without sending emails or blocking payments.

When you want FluxRules to keep track of the code behind each name, register
a handler in the action registry, described below.

## Actions in rules

A rule takes one action with `action`, or several with `actions`:

```python
from fluxrules import F, Rule
from fluxrules.engine.phreak import PhreakEngine

rule1 = Rule(
    name="check_high_value",
    conditions=F("amount") > 5000,
    action="require_approval",
)

rule2 = Rule(
    name="check_fraud",
    conditions=F("ip_risk_score") > 80,
    actions=("block", "notify_security"),
)

engine = PhreakEngine()
engine.load_rules([rule1, rule2])

result = engine.evaluate({"amount": 7500, "ip_risk_score": 90})
print(f"Actions: {result.actions}")
```

- `action="require_approval"` gives the rule a single action name.
- `actions=("block", "notify_security")` gives it several, in the order they
  should run.

`result.actions` lists the actions of every fired rule, in firing order. Any
string is a valid action name.

## Registering a handler

The `@action` decorator registers a function under an action name:

```python
from fluxrules.plugins.actions import action, action_registry


@action(
    name="send_approval_request",
    description="Send an approval request to the team",
    category="notifications",
)
def send_approval_request(transaction_id: str, amount: int) -> dict:
    print(f"Sending approval request for {transaction_id} ({amount})")
    return {"sent": True}


outcome = action_registry.execute("send_approval_request", transaction_id="TXN-123", amount=7500)
print(outcome)  # {'success': True, 'action': 'send_approval_request', 'result': {'sent': True}}
```

The decorator takes these options:

- `name`: the action name that rules use. It must be unique.
- `description`: a short text that tools and listings show.
- `category`: a label for grouping related actions. The default is
  `"general"`.
- `async_handler`: set to `True` when the function is `async`. The default is
  `False`.

`action_registry.execute(name, **kwargs)` calls the handler with the keyword
arguments you pass. Before calling, it checks that every required parameter
is present and that no unknown ones are passed, and raises `ValueError` if
not. It returns a dictionary with `success`, `action`, and either `result` or
`error`. A handler that raises does not stop your program: the error is
logged and returned under `error` with `success` set to `False`.

## Running the actions of a result

A common pattern is to evaluate a fact and then run the handler for each
fired action. A handler that declares `**fact` accepts every field of the
fact, so you can pass the whole fact to it:

```python
@action(name="notify_security", category="notifications")
def notify_security(**fact) -> dict:
    return {"notified": True, "amount": fact.get("amount")}


fact = {"amount": 7500, "ip_risk_score": 90}
result = engine.evaluate(fact)

for name in result.actions:
    if action_registry.has(name):
        print(action_registry.execute(name, **fact))
    else:
        print(f"No handler for {name!r}; the application handles it")
```

`action_registry.has(name)` tells you whether a handler is registered, so
action names without a handler can fall through to your own code.

## Async handlers

Register an `async` function with `async_handler=True`, and run it with
`execute_async`:

```python
import asyncio


@action(name="log_to_database", category="logging", async_handler=True)
async def log_to_database(event_id: str) -> dict:
    return {"logged": True, "event_id": event_id}


outcome = asyncio.run(action_registry.execute_async("log_to_database", event_id="evt-1"))
print(outcome["result"])  # {'logged': True, 'event_id': 'evt-1'}
```

`execute` refuses an async handler, and `execute_async` refuses a plain one.
Each raises `ValueError` that says which method to use instead.

## Inspecting the registry

Every registered action keeps its metadata:

```python
print(action_registry.list_actions())  # every registered name

info = action_registry.get("send_approval_request")
print(info.name, info.category, info.description)

notifications = action_registry.get_actions_by_category("notifications")
print([a.name for a in notifications])

print(action_registry.get_action_signature("send_approval_request"))
# send_approval_request(transaction_id: str, amount: int) -> dict
```

- `list_actions()` returns every registered name.
- `get(name)` returns the metadata of one action, or `None`.
- `get_actions_by_category(category)` returns the metadata of every action in
  that category.
- `get_action_signature(name)` returns the handler's parameters and return
  type as text.

## Patterns

### Choosing behavior from the fact

A handler can read the fact and decide what to do:

```python
@action(name="escalate", description="Escalate by amount")
def escalate(**fact) -> dict:
    amount = fact.get("amount", 0)
    if amount > 50000:
        level = "executive"
    elif amount > 10000:
        level = "manager"
    else:
        level = "standard"
    return {"escalated_to": level}
```

### Chaining actions

A handler can run other registered actions in a fixed order:

```python
@action(name="block_transaction")
def block_transaction(**fact) -> dict:
    return {"blocked": True}


@action(name="notify_then_block")
def notify_then_block(**fact) -> dict:
    action_registry.execute("notify_security", **fact)
    action_registry.execute("block_transaction", **fact)
    return {"status": "complete"}
```

Often it is simpler to list both names in the rule with
`actions=("notify_security", "block_transaction")` and let the dispatch loop
above run them in order.

---

## Next Steps

- **Rule Lifecycle**: See [Rule Lifecycle](rule-lifecycle.md) for creating, updating and deleting rules
- **Example 15**: See [Action System](https://github.com/saurabh2mishra/fluxrules/blob/main/examples/15_action_system.py) for handlers and dispatch
- **Example 21**: See [Action Registry](https://github.com/saurabh2mishra/fluxrules/blob/main/examples/21_action_registry.py) for metadata, categories and async handlers
