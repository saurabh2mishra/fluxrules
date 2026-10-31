# Rule Builder

**Prerequisites:** [Concepts](concepts.md) (Rule), [Authoring Rules](authoring-rules.md) and [Conditions](conditions.md) (condition tree).

---

`RuleBuilder` is a fluent API for constructing rules step by step. It validates
as you go and `build()` returns the same canonical `Rule` every other authoring
path produces, so the result goes straight into an engine with no conversion.

## Basic usage

`.condition()` accepts an `F` expression or a raw dict; both compile to the
same condition tree.

```python
from fluxrules import F, PhreakEngine, RuleBuilder

rule = (
    RuleBuilder()
    .name("high_value_transaction")
    .group("fraud_detection")
    .tag("tier_1", "manual_review")
    .priority(10)
    .condition(F("amount") > 5000)
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
from fluxrules import F, RuleBuilder, evaluate

rule = (
    RuleBuilder()
    .name("adult")
    .condition(F("age") >= 18)
    .action("allow")
    .build()
)

print(evaluate(rule, {"age": 30}).fired_rules)
```

## Fluent API

| Method | Purpose | Returns |
|--------|---------|---------|
| `.name(str)` | Set rule name (required) | Builder |
| `.condition(F(...) or dict)` | Set the condition tree from an `F` expression or a raw dict (required) | Builder |
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
from fluxrules import F, RuleBuilder, evaluate

rule = (
    RuleBuilder()
    .name("escalate")
    .condition(F("risk") > 90)
    .action("notify_compliance")
    .action("freeze_account")
    .build()
)

result = evaluate(rule, {"risk": 95})
print(result.actions)
```

## Building complex conditions

Compose conditions with `&`, `|`, and `~` directly on `F` expressions:

```python
from fluxrules import F, PhreakEngine, RuleBuilder

rule = (
    RuleBuilder()
    .name("complex_rule")
    .condition(
        (F("amount") > 5000) & (F("country").isin(["NG", "GH"]))
    )
    .action("review")
    .build()
)

engine = PhreakEngine()
engine.load_rules([rule])
print(f"Fired: {engine.evaluate({'amount': 6000, 'country': 'NG'}).fired_rules}")
```

`ConditionBuilder` is still available for dict-based composition but is
superseded by the F DSL for new code.

## Validation

The builder fails at the point of the mistake rather than at evaluation time.
`.condition()` parses the condition tree immediately, and `.build()` enforces that the
required fields are present.

```python
from fluxrules import F, RuleBuilder
from fluxrules.exceptions import RuleValidationError

try:
    RuleBuilder().condition(F("x") > 1).build()
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

- **Rule Lifecycle**: See [Rule Lifecycle](rule-lifecycle.md) for CRUD operations
- **Conditions**: See [Conditions](conditions.md) for condition operators
- **Example**: See [Example 18: Unified Rule](https://github.com/saurabh2mishra/fluxrules/blob/main/examples/18_unified_rule.py) for working code
