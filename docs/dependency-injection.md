# Dependency Injection

**Prerequisites:** [Custom Actions](custom-actions.md) and [Custom Engines](custom-engines.md).

---

FluxRules is designed for manual dependency injection via constructor parameters.

## Pattern

```python skip
from fluxrules.engine.phreak import PhreakEngine

# Inject dependencies
logger = get_logger("fluxrules")
metrics = get_metrics_collector()
database = get_database_connection()

# Pass to engine
engine = PhreakEngine(metrics_collector=metrics, logger=logger)


# Or to action
@action(name="log_and_store")
def log_and_store(database=database, logger=logger, **kwargs):
    logger.info(f"Storing: {kwargs}")
    database.insert(kwargs)
    return {"stored": True}
```

## No framework dependency

FluxRules has zero framework dependencies. Integrate with your existing DI setup:

```python skip
# FastAPI
from fastapi import Depends


@app.post("/evaluate")
def evaluate(request: Request, engine: Engine = Depends(get_engine)):
    return engine.evaluate(request.facts)


# Django
from django.shortcuts import get_object_or_404


def evaluate_view(request):
    engine = get_engine()  # From your service layer
    return engine.evaluate(request.POST)
```

---

## Next Steps

- **Custom Engines** — See [Custom Engines](custom-engines.md)
- **Custom Actions** — See [Custom Actions](custom-actions.md)
