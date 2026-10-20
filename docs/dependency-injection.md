# Dependency Injection

**Prerequisites:** [Custom Actions](custom-actions.md) and [Custom Engines](custom-engines.md).

---

FluxRules is designed for manual dependency injection via constructor parameters.

## Pattern

```python
# python skip
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

```python
# python skip
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

## ServiceFactory and persistence

When you register a persistence adapter via `ServiceFactory.create_persistence_adapter()`,
`Rule(persist=True)` and `Rule.save()` automatically delegate to that adapter rather
than the built-in SQLite default. This is the recommended pattern for production
deployments that use PostgreSQL, SQL Server, or another provider:

```python
# python skip - requires a live database and session provider
from fluxrules.di import ServiceFactory
from fluxrules.config import RuntimeConfig, PersistenceConfig

ServiceFactory.create_persistence_adapter(
    session_provider=SessionLocal,          # your SQLAlchemy sessionmaker
    config=RuntimeConfig(
        persistence=PersistenceConfig(backend="postgres")
    ),
)
```

See [Persistence](persistence.md#using-a-different-sql-provider-postgres-sql-server-etc) for a full example.

---

## Next Steps

- **Persistence** - See [Persistence](persistence.md) for database configuration
- **Custom Engines** - See [Custom Engines](custom-engines.md)
- **Custom Actions** - See [Custom Actions](custom-actions.md)
