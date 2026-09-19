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

## Dependency Extras

Configuration scope changes with installed extras:

- `api` enables FastAPI server components.
- `sql` enables SQLAlchemy and Alembic integration.
- `redis` enables Redis adapters.
- `otel` enables OpenTelemetry exporters.
