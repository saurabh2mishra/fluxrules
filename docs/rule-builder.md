# Rule Builder

**Prerequisites:** [Concepts](concepts.md) (Rule) and [Conditions](conditions.md) (DSL).

---

`RuleBuilder` is a fluent API for constructing rules step by step. It validates
as you go and `build()` returns the same canonical `Rule` every other authoring
path produces, so the result goes straight into an engine with no conversion.

## Basic usage

```python
from fluxrules import PhreakEngine, RuleBuilder

rule = (
    RuleBuilder()
    .name("high_value_transaction")
    .group("fraud_detection")
    .tag("tier_1", "manual_review")
    .priority(10)
    .condition({"type": "condition", "field": "amount", "op": ">", "value": 5000})
    .action("require_approval")
    .build()
)

engine = PhreakEngine()
engine.load_rules([rule])
result = engine.evaluate({"amount": 7500})
print(f"Fired: {result.fired_rules}")
```

`build()` returns a `Rule`, so it also works with the top-level `evaluate()`:

```python
from fluxrules import RuleBuilder, evaluate

rule = (
    RuleBuilder()
    .name("adult")
    .condition({"type": "condition", "field": "age", "op": ">=", "value": 18})
    .action("allow")
    .build()
)

print(evaluate(rule, {"age": 30}).fired_rules)
```

## Fluent API

| Method | Purpose | Returns |
|--------|---------|---------|
| `.name(str)` | Set rule name (required) | Builder |
| `.condition(dict)` | Set condition DSL, parsed and validated now (required) | Builder |
| `.action(str)` | Append an action; call repeatedly for several | Builder |
| `.priority(int)` | Set priority, higher evaluates first | Builder |
| `.group(str)` | Set the group/domain | Builder |
| `.description(str)` | Set a human-readable description | Builder |
| `.tag(*str)` | Add tags | Builder |
| `.enabled(bool)` | Set the enabled flag | Builder |
| `.persist(bool)` | Store the built rule in the database | Builder |
| `.status(RuleStatus)` | Set lifecycle status | Builder |
| `.created_by(str)` | Record the author | Builder |
| `.build()` | Create the rule | `Rule` |
| `.build_engine_rule()` | Create the internal representation | `EngineRule` |
| `.to_dict()` | Create the canonical rule mapping | `dict` |

`RuleBuilder()` generates an ID automatically; pass one explicitly with
`RuleBuilder(42)` when you need a specific ID.

## Multiple actions

Call `.action()` once per action. They fire in the order added.

```python
from fluxrules import RuleBuilder, evaluate

rule = (
    RuleBuilder()
    .name("escalate")
    .condition({"type": "condition", "field": "risk", "op": ">", "value": 90})
    .action("notify_compliance")
    .action("freeze_account")
    .build()
)

result = evaluate(rule, {"risk": 95})
print(result.actions)
```

## Building complex conditions

`ConditionBuilder` assembles nested boolean logic without writing DSL dicts by
hand.

```python
from fluxrules import ConditionBuilder, PhreakEngine, RuleBuilder

cb = ConditionBuilder()
dsl = cb.and_group(
    {"type": "condition", "field": "amount", "op": ">", "value": 5000},
    {"type": "condition", "field": "country", "op": "in", "value": ["NG", "GH"]},
).build()

rule = RuleBuilder().name("complex_rule").condition(dsl).action("review").build()

engine = PhreakEngine()
engine.load_rules([rule])
print(f"Fired: {engine.evaluate({'amount': 6000, 'country': 'NG'}).fired_rules}")
```

Use `.or_group(...)` the same way for disjunctions, and nest the dicts it
returns to build deeper trees.

## Validation

The builder fails at the point of the mistake rather than at evaluation time.
`.condition()` parses the DSL immediately, and `.build()` enforces that the
required fields are present.

```python
from fluxrules import RuleBuilder
from fluxrules.exceptions import RuleValidationError

try:
    RuleBuilder().condition(
        {"type": "condition", "field": "x", "op": ">", "value": 1}
    ).build()
except RuleValidationError as e:
    print(f"Invalid rule: {e}")
```

## Persistence

Building a rule performs no I/O. Pass `.persist(True)` to store it as it is
built, or call `Rule.save()` later:

```python
# python skip
rule = RuleBuilder().name("r").condition(dsl).action("a").persist(True).build()

# equivalently, decide after the fact:
rule = RuleBuilder().name("r").condition(dsl).action("a").build()
rule.save()
```

---

## Next Steps

- **Rule Lifecycle** - See [Rule Lifecycle](rule-lifecycle.md) for CRUD operations
- **Conditions** - See [Conditions](conditions.md) for DSL operators
- **Example** - See [Example 18: Unified Rule](https://github.com/saurabh2mishra/fluxrules/blob/main/examples/18_unified_rule.py) for working code
