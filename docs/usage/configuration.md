# Configuration

## Engine Configuration

Engine defaults are managed through `fluxrules.engine.configuration`.

```python
from fluxrules.engine.configuration import get_config

cfg = get_config()
print(cfg.rule_engine_type)
```

## Strict Fact Validation

Engine evaluation supports optional strict fact pre-flight validation:

```python
from fluxrules import PhreakEngine

engine = PhreakEngine()
result = engine.evaluate({"amount": 100}, strict_facts=True)
```

When enabled, invalid fact structures fail fast.

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
