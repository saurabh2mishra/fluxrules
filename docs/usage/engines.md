# Engine Selection

## Available Engine

- `fluxrules.engine.phreak.PhreakEngine` (the single production engine)

## General Guidance

- PHREAK is the de-facto engine for FluxRules; there is no engine to choose.
- Pick an evaluation mode: stateless (default) or streaming (`streaming_mode=True`).
- Benchmark against your own facts and rule patterns before production rollout.

> Note: The simple linear evaluator that backs `RuleService` is
> `fluxrules.services.reference_evaluator.ReferenceEvaluator`. It is a
> reference implementation of the service `EnginePort`, **not** a selectable
> single-fact engine, and is not available through `get_engine()`.

## Engine-Level Evaluation

```python
from fluxrules.engine.phreak import PhreakEngine
from fluxrules.domain.unified_rule import Rule

engine = PhreakEngine()
engine.load_rules([
    Rule(
        id=1,
        name="high_value",
        condition_dsl={"type": "condition", "field": "amount", "op": ">", "value": 1000},
        action="review",
    )
])

result = engine.evaluate({"amount": 1200})
print(result.fired_rules)
```
