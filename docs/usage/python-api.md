# Python API

**Prerequisites:** [Quickstart](../quickstart.md), [Concepts](../concepts.md).

---

## Quick Evaluation

Use the engine directly for simple cases:

```python
from fluxrules import F, Rule
from fluxrules.engine.phreak import PhreakEngine

# Define rules
rule = Rule(
    name="high_value",
    conditions=F("amount") > 1000,
    action="flag"
)

engine = PhreakEngine()
engine.load_rules([rule])

# Evaluate
result = engine.evaluate({"amount": 2500})
print(f"Matched: {result.fired_rules}")      # [1]
print(f"Actions: {result.actions}")          # ["flag"]
print(f"Latency: {result.latency_ms} ms")    # ~2ms
```

## Validation

Validate rules before use:

```python
from fluxrules import F, Rule
from fluxrules.services.rule_service import RuleService

# Create a rule and service
rule = Rule(
    name="check",
    conditions=F("status") == "active",
    action="proceed"
)

service = RuleService.create()
# Validation is automatic during evaluation
```

## Engines (Direct)

For more control, use engines directly:

```python
from fluxrules import F, Rule
from fluxrules.engine.phreak import PhreakEngine

rule1 = Rule(name="rule1", conditions=F("status") == "active", action="flag")
rule2 = Rule(name="rule2", conditions=F("amount") > 5000, action="review")

engine = PhreakEngine()
engine.load_rules([rule1, rule2])

result = engine.evaluate({"amount": 2500})
```

## Many facts at once

`engine.evaluate_batch(facts)` evaluates a list of facts and returns a list of
results, one per fact, in the same order. Each result is the same
`EvaluationResult` that `evaluate()` returns, so you get the fired rules,
their actions, the explanations and the latency for every fact:

```python
from fluxrules import F, Rule
from fluxrules.engine.phreak import PhreakEngine

engine = PhreakEngine()
engine.load_rules([Rule(id=1, name="big", conditions=F("amount") > 1000, action="review")])

facts = [{"amount": 50}, {"amount": 4200}, {"amount": 900}]
results = engine.evaluate_batch(facts)

assert [r.fired_rules for r in results] == [[], [1], []]
assert results[1].actions == ["review"]
```

Without `workers`, this is the same as writing
`[engine.evaluate(f) for f in facts]`. It accepts any iterable, so a generator
works too.

### Using several CPU cores

Python runs one thread of Python code at a time, so a single process uses one
CPU core. To use more, pass `workers`:

```python
results = engine.evaluate_batch(facts, workers=4)
```

This starts 4 worker processes and splits the facts between them. Each worker
builds its own copy of your engine, with the same rules and the same settings:
`fact_schema`, `validate_facts`, `on_invalid`, `fact_pipeline`,
`compile_conditions` and the `EngineConfig`. The results are identical to the
single-process ones and come back in input order.

Things to know when you use `workers`:

- **Starting processes takes time.** Workers pay off for thousands of facts or
  expensive rules, not for a handful. `workers` larger than the number of facts
  is reduced to the number of facts.
- **Guard your script.** On macOS and Windows each worker imports your script
  again. Put the code that calls `evaluate_batch` under
  `if __name__ == "__main__":`, or every worker would start the batch again.
- **Settings must be picklable.** Workers receive the settings by pickling
  them. A `lambda`, or a class defined inside a function, cannot be pickled, so
  `Filter(lambda f: ...)` in a pipeline raises a clear `ValueError` before any
  worker starts. Use a named function defined at the top level of a module.
- **Invalid facts behave as in a loop.** With `on_invalid="quarantine"`,
  rejected facts get an empty result and are added to
  `engine.quarantined_facts`, in input order. With `on_invalid="raise"`, the
  error for the first invalid fact is raised.
- **Not for streaming mode.** A streaming engine remembers the previous fact,
  and splitting facts between processes would split that memory. A streaming
  engine accepts only `workers=1`.

### Facts from a database

Read the rows with your own query, build the engine once, and keep the row key
next to each result. With SQLAlchemy, `.mappings()` gives each row as a
dictionary:

```python
from sqlalchemy import create_engine, text

from fluxrules import F, Rule
from fluxrules.engine.phreak import PhreakEngine

db = create_engine("sqlite://")
with db.begin() as conn:
    conn.execute(text("CREATE TABLE payments (id INTEGER, amount REAL, country TEXT)"))
    conn.execute(
        text("INSERT INTO payments VALUES (1, 50, 'US'), (2, 4200, 'DE'), (3, 9000, 'FR')")
    )

rules_engine = PhreakEngine()
rules_engine.load_rules(
    [Rule(id=1, name="big", conditions=F("amount") > 1000, action="review")]
)

with db.connect() as conn:
    rows = conn.execute(text("SELECT id, amount, country FROM payments")).mappings().all()

results = rules_engine.evaluate_batch(rows)
flagged = [row["id"] for row, result in zip(rows, results, strict=True) if result.fired_rules]
assert flagged == [2, 3]
```

For a very large table, read and evaluate it in chunks (for example 10,000
rows at a time) instead of loading every row first.

## RuleService (Sessions & Persistence)

Use `RuleService` for stateful workflows:

```python
# python skip
from fluxrules.services.rule_service import RuleService

service = RuleService.create()

# Create session requires ruleset_id
# ruleset_id = service.save_ruleset(name="payment_rules", rules=rules)
# session = service.create_session(ruleset_id)

# Add facts and evaluate
# session.assert_fact({"customer_id": "c1", "amount": 5000})
# result = session.evaluate()
# print(f"Matched: {result.fired_rules}")
```

---

## Next Steps

- **Ways to Evaluate a Fact**: See [Ways to Evaluate a Fact](../evaluating-facts.md) for every way to evaluate facts, side by side
- **Engines**: See [The FluxRules Engine](../engine-comparison.md)
- **Sessions**: See [Sessions](../sessions.md) for stateful workflows
- **API Reference**: See [Reference: Public API](../reference/public-api.md)
