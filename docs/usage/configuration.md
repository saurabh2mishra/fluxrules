# Configuration

## Engine Configuration

Engine defaults are managed through `fluxrules.engine.configuration`.

```python
from fluxrules.engine.configuration import get_config

cfg = get_config()
print(cfg.rule_engine_type)
```

### Changing settings after the engine is created

`PhreakEngine` uses the config object it was created with: the `config` you
pass, or the process-wide config if you pass none. If you change a field on
that object later, the engine uses the new value from its next evaluation on.
This holds for rules run by the interpreter and for rules compiled with
`compile_conditions=True` (the engine recompiles them when a condition setting
changes):

```python
from fluxrules import F, Rule
from fluxrules.engine.configuration import EngineConfig
from fluxrules.engine.phreak import PhreakEngine

config = EngineConfig(missing_field="false")
engine = PhreakEngine(config=config, compile_conditions=True)
engine.load_rules([Rule(id=1, name="r", conditions=~(F("blocked") == True), action="allow")])  # noqa: E712
assert engine.evaluate({"amount": 1}).fired_rules == [1]

config.missing_field = "unknown"  # takes effect on the next evaluation
assert engine.evaluate({"amount": 1}).fired_rules == []
```

`set_config(new_config)` is different: it replaces the process-wide object
instead of changing it. Engines created before the call keep the object they
already had. Engines created afterwards, and `fluxrules.evaluate()`, use the
new one.

`evaluate_batch(facts, workers=N)` sends the config's current values to its
worker processes when you call it.

## Strict Fact Validation

Engine evaluation supports optional strict fact pre-flight validation:

```python
from fluxrules import PhreakEngine

engine = PhreakEngine()
result = engine.evaluate({"amount": 100}, strict_facts=True)
```

`strict_facts=True` checks the fact before any rule runs, and raises
`InvalidFactError` (from `fluxrules.pipeline.validators`, a subclass of
`ValueError`) when it is not a valid fact:

```python
from fluxrules.pipeline.validators import InvalidFactError

try:
    engine.evaluate(["not", "a", "fact"], strict_facts=True)
except InvalidFactError as e:
    print(f"Rejected: {e}")
```

Without `strict_facts`, the same input raises `TypeError` instead. Catch the
exception that matches the mode you use.

## Missing Fields Under NOT

`EngineConfig.missing_field` decides whether `~(F("blocked") == True)` fires on
a fact with no `blocked` key:

```python
from fluxrules import EngineConfig
from fluxrules.engine.phreak import PhreakEngine

engine = PhreakEngine(config=EngineConfig(missing_field="unknown"))  # 2.0 behaviour
```

- `None` (default): fires, and warns once per `NOT` with `MissingFieldNotWarning`.
- `"false"`: fires, no warning (1.x behaviour).
- `"unknown"`: does not fire; a missing field is unknown, as SQL treats `NULL`.

See [Missing fields and NOT](../conditions.md#missing-fields-and-not).

## Typed Facts

Engines take optional keywords for typed facts:

```python
from pydantic import BaseModel

from fluxrules.engine.phreak import PhreakEngine


class Customer(BaseModel):
    user_age: int


engine = PhreakEngine(
    fact_schema=Customer,  # rules are checked against Customer at load_rules
    validate_facts="normalize",  # "off" (default) | "normalize" | "strict"
    on_invalid="quarantine",  # "raise" (default) | "skip" | "quarantine"
)
```

See [Typed Facts](../typed-facts.md).

## Dependency Extras

Configuration scope changes with installed extras:

- `api` enables FastAPI server components.
- `sql` enables SQLAlchemy and Alembic integration.
- `redis` enables Redis adapters.
- `otel` enables OpenTelemetry exporters.
