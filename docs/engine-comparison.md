# The FluxRules Engine: PHREAK

**Prerequisites:** [Concepts](concepts.md) (Engine).

---

FluxRules is built on a single production engine: **PHREAK**, a lazy,
agenda-driven matching algorithm. There is no engine to choose — the design goal
is one fast, memory-efficient engine that covers every supported use case.

PHREAK exposes two **evaluation modes** on the same engine, plus a dependency-free
**reference evaluator** used internally as a correctness oracle.

## Modes at a glance

| Property | Stateless mode | Streaming mode |
|----------|----------------|----------------|
| **Call shape** | Full re-evaluation per call | Delta-driven (incremental) |
| **Return value** | Full fired set every call | Fired delta since last fact |
| **State** | None kept between calls | Working memory persists |
| **Best for** | HTTP/request-response, batch | Long-lived sessions, event streams |
| **Default** | ✅ Yes | Opt-in (`streaming_mode=True`) |

Both modes share the same operator evaluator and configuration surface, so a fact
that fires a rule in one mode fires the same rule in the other on first sight.

## Stateless mode (default)

**Algorithm:** Lazy, on-demand evaluation. Rules are loaded once; each `evaluate`
call matches the fact map it is given and returns the complete fired set.

**Best for:**
- API/request-response (HTTP, batch)
- Rules added/removed dynamically
- Low memory footprint preferred

**Example:**
```python
from fluxrules import Rule
from fluxrules.engine.phreak import PhreakEngine

rule1 = Rule(name="rule1", condition_dsl={"type": "condition", "field": "amount", "op": ">", "value": 5000}, action="flag")
rule2 = Rule(name="rule2", condition_dsl={"type": "condition", "field": "country", "op": "==", "value": "US"}, action="allow")
rules = [rule1, rule2]

engine = PhreakEngine()
engine.load_rules(rules)

# Single evaluation
result = engine.evaluate({"amount": 6000, "country": "US"})
print(f"Fired: {result.fired_rules}")

# Multiple independent evaluations
facts = [{"amount": 3000, "country": "NG"}, {"amount": 7000, "country": "US"}]
for fact in facts:
    result = engine.evaluate(fact)  # Fresh evaluation each time
    print(f"Fact {fact}: Fired {result.fired_rules}")
```

**Memory profile:** O(1) per evaluation (rules loaded once, facts evaluated independently).

## Streaming mode

**Algorithm:** The same PHREAK network, but working memory persists across calls.
A fact seen for the first time reports the full fired set; re-evaluating an
unchanged fact reports an empty delta.

**Best for:**
- Long-lived sessions (repeated assert/retract)
- Event streams where only changes matter

**Example:**
```python
from fluxrules.engine.phreak import PhreakEngine

engine = PhreakEngine(streaming_mode=True)
engine.load_rules(rules)

# First sight of a fact reports the full fired set
result = engine.evaluate({"amount": 6000, "country": "US"})
```

See [Working Memory](working-memory.md) for the streaming contract in full.

## Reference evaluator (correctness oracle)

`fluxrules.services.reference_evaluator.ReferenceEvaluator` is a small,
deterministic, dependency-free evaluator. It is **not** a selectable engine — it
is the default `RuleService` engine and an independent oracle the test suite
checks PHREAK against, so shared-code defects cannot hide behind a single
implementation.

---

## Next Steps

- **Choosing an Engine** — See [Choosing an Evaluation Mode](choosing-an-engine.md) for mode-selection logic
- **Engine Limits** — See [Engine Scope and Limits](engine-scope-and-limits.md)
