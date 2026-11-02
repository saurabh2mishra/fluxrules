# Quickstart

This page takes you from an empty script to working rules in a few minutes.

**Prerequisites:** Python 3.11 or newer, and FluxRules installed (see
[Installation](installation.md)).

---

## Your first rule

```python
from fluxrules import F, Rule, evaluate

rule = Rule(id=1, name="adult", conditions=F("age") >= 18, action="allow")

result = evaluate(rule, {"age": 30})
print(result.fired_rules)  # [1], the id of the rule that matched
print(result.actions)      # ['allow']
```

A **rule** pairs a condition with an action. `F("age") >= 18` is the
condition: it holds when the field `age` is 18 or more. The dictionary
`{"age": 30}` is a **fact**, the data you want to check. `evaluate()` runs the
rule against the fact and returns a result that lists the rules that matched
(`fired_rules`) and the actions they ask for (`actions`).

[Concepts](concepts.md) explains rules, facts and results in more detail.

## Using an engine

`evaluate()` is handy for a quick check. When you evaluate many facts against
the same rules, load the rules into an engine once and reuse it:

```python
from fluxrules import F, PhreakEngine, Rule

rule = Rule(
    id=1,
    name="high_value_transaction",
    domain="fraud_detection",
    conditions=F("amount") > 5000,
    action="manual_review",
    priority=100,
)

engine = PhreakEngine()
engine.load_rules([rule])

result = engine.evaluate({"amount": 6000})
print(f"Matched rules: {result.fired_rules}")
print(f"Actions: {result.actions}")
```

**Output:**
```
Matched rules: [1]
Actions: ['manual_review']
```

This rule uses three more options:

- `id` gives the rule a fixed id. Without it, FluxRules numbers rules in the
  order you create them, counting across your whole program. This page sets
  ids so the printed output stays the same however you run the examples.
- `domain` names the problem area the rule belongs to. You can use it to
  load or filter a group of rules. See [Domains and Tags](domains-and-tags.md).
- `priority` sets the order in which matching rules fire. A higher number
  fires first. Every matching rule still fires; priority only sets the order.

## Combining checks with AND, OR and NOT

A condition can combine several checks:

```python
from fluxrules import F, PhreakEngine, Rule

rule = Rule(
    id=1,
    name="risky_payment",
    conditions=(
        (F("amount") > 2000)
        & ((F("country").isin(["NG", "SN"])) | (F("ip_risk_score") >= 70))
        & ~(F("verified_user") == True)
    ),
    action="block_payment",
)

engine = PhreakEngine()
engine.load_rules([rule])

result = engine.evaluate({"amount": 3000, "country": "NG", "verified_user": False})
print(result.fired_rules)  # [1]
```

`&` means both sides must hold, `|` means either side is enough, and `~` means
the check must not hold. Wrap each comparison in parentheses, because `&`, `|`
and `~` bind more tightly than `>` and `==` in Python.
[Complex Conditions](complex-conditions.md) covers nesting in depth.

## Several rules at once

Pass a list to `load_rules`. Each fact is checked against every rule:

```python
from fluxrules import F, PhreakEngine, Rule

rules = [
    Rule(id=1, name="high_value", conditions=F("amount") > 5000, action="manual_review"),
    Rule(
        id=2,
        name="high_risk_country",
        conditions=F("country").isin(["NG", "SN"]),
        action="block_payment",
    ),
]

engine = PhreakEngine()
engine.load_rules(rules)

result = engine.evaluate({"amount": 3000, "country": "NG"})
print(f"Matched: {result.fired_rules}")  # [2] (high_risk_country)
print(f"Actions: {result.actions}")      # ['block_payment']
```

Only the second rule matches, because the amount is not over 5000.

---

## Next steps

- [Concepts](concepts.md): the words used across these docs.
- [From Fact to Action](fact-to-action.md): what happens to a fact inside
  the engine.
- [Conditions](conditions.md): every operator you can use in a condition.
- [Examples and Learning Path](examples.md): runnable scripts that build on
  each other, from the first rule to fact pipelines.
