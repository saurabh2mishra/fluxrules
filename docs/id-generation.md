# ID Generation

**Prerequisites:** [Concepts](concepts.md) (Rule).

---

FluxRules automatically generates rule IDs. By default, IDs are sequential integers (1, 2, 3, ...).

## Auto-generated IDs

```python
from fluxrules import Rule

rule1 = Rule(
    name="check_1",
    condition_dsl={"type": "condition", "field": "amount", "op": ">", "value": 0},
    persist=False,
)
print(rule1.id)  # 1

rule2 = Rule(
    name="check_2",
    condition_dsl={"type": "condition", "field": "amount", "op": ">", "value": 0},
    persist=False,
)
print(rule2.id)  # 2
```

## Custom IDs

Override auto-generation with the `id` parameter:

```python
rule = Rule(
    id=999,  # Custom ID
    name="custom_id_rule",
    condition_dsl={"type": "condition", "field": "amount", "op": ">", "value": 0},
    persist=False,
)
print(rule.id)  # 999
```

## ID persistence

- **`persist=False`** (default) - In-memory auto-increment per Rule instance
- **`persist=True`** - ID from database auto-increment. `Rule.save()` does the
  same thing for a rule that already exists in memory.

When you persist rules to the database, the database assigns final IDs:

```python
from fluxrules.domain.models import Ruleset
from fluxrules.services.rule_service import RuleService

service = RuleService.create()
rule = Rule(
    name="will_be_persisted",
    condition_dsl={"type": "condition", "field": "amount", "op": ">", "value": 0},
    persist=True,  # Will store in database
)

service.persist(Ruleset(group="default", rules=(rule.to_engine_rule(),)))
# After persist, rule.id is set from database
```

## ID uniqueness

- Within a process: Rule IDs are unique
- Across persistence: Database ensures uniqueness per ruleset
- Conflict handling: Pass explicit `id=` to avoid conflicts

---

## Next Steps

- **Rule Lifecycle** - See [Rule Lifecycle](rule-lifecycle.md) for rule creation and deletion
- **Persistence** - See [Persistence](persistence.md) for database ID management
