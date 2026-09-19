# Rule Types

**Prerequisites:** [Concepts](concepts.md).

This page explains the boundary between the public `Rule` authoring type and
the internal `EngineRule` representation. Condition syntax belongs to
[Conditions](conditions.md), and engine-mode selection belongs to
[Choosing an Engine](choosing-an-engine.md).

## Public `Rule`

`Rule` is the public type for authoring and serialization. Its `condition_dsl`
tree is the source of truth for boolean logic. Set `persist=False` in examples
and tests to avoid writing to the configured database.

```python
from fluxrules import Rule

rule = Rule(
    name="adult",
    condition_dsl={"type": "condition", "field": "age", "op": ">=", "value": 18},
    actions=("allow", "audit"),
    persist=False,
)

assert rule.action == "allow"  # compatibility view of actions[0]
assert rule.actions == ("allow", "audit")
```

See [Concepts](concepts.md) and the [Pydantic Rule Guide](pydantic-rule-guide.md)
for the complete field reference.

## `RuleBuilder`

`RuleBuilder` is a fluent adapter for workflows that assemble a rule
incrementally. Its `build()` method returns an `EngineRule`, not the public
`Rule`. Use `to_dict()` when the result must enter the public authoring path.

```python
from fluxrules.domain.rule_builder import RuleBuilder

engine_rule = (
    RuleBuilder(rule_id=1, persist=False)
    .name("High Value Transaction")
    .group("fraud_detection")
    .priority(10)
    .condition({"type": "condition", "field": "amount", "op": ">", "value": 10000})
    .action("flag_for_review")
    .build()
)

assert engine_rule.condition_dsl["type"] == "condition"
```

Implementation: `src/fluxrules/domain/rule_builder.py`.

## Internal `EngineRule`

`EngineRule` is immutable and is used by the reference evaluator, persistence
adapters, and internal services. Its authoritative logic is always the full
`condition_dsl` tree. Its `.conditions` member is a derived flat leaf view for
compatibility; it cannot preserve `OR`, `NOT`, or nesting and must not be used
to rebuild rule logic.

Convert explicitly at an internal integration boundary:

```python
from fluxrules import Rule

rule = Rule(
    name="adult",
    condition_dsl={"type": "condition", "field": "age", "op": ">=", "value": 18},
    action="allow",
    persist=False,
)

engine_rule = rule.to_engine_rule()
round_tripped = Rule.from_engine_rule(engine_rule, persist=False)

assert round_tripped.condition_dsl == rule.condition_dsl
```

Implementation: `src/fluxrules/domain/models.py`; conversion methods:
`src/fluxrules/domain/unified_rule.py`.

## Engine Input Contracts

| API | Accepted input | Output or behavior |
|---|---|---|
| `PhreakEngine.load_rules(rules)` | Public `Rule` objects or rule dictionaries | Loads rules for stateless or streaming PHREAK evaluation |
| `ReferenceEvaluator.evaluate(ruleset, facts)` | A `Ruleset` containing `EngineRule` objects | Returns `EvaluationResult` with matched IDs and ordered actions |
| `Rule.to_engine_rule()` | One public `Rule` | Produces the immutable internal representation |
| `Rule.from_engine_rule(engine_rule)` | One `EngineRule` | Produces a public `Rule`; persistence is disabled by default |

For normal application code, create `Rule` objects and pass them to
`PhreakEngine.load_rules()`. Use `EngineRule` and `ReferenceEvaluator` at
internal adapter, persistence, or parity-test boundaries.

## Next Steps

- [Getting Started](quickstart.md)
- [Conditions](conditions.md)
- [Choosing an Engine](choosing-an-engine.md)
- [Domains and Tags](domains-and-tags.md)
