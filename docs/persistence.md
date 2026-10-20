# Persistence

**Prerequisites:** [Concepts](concepts.md) (Rule) and [Sessions](sessions.md) (RuleService).

---

FluxRules rules can be persisted to a database. Use persistence when you need to:

1. **Store rules permanently** - survive application restarts
2. **Share rules across instances** - load the same ruleset in multiple processes
3. **Audit trail** - track rule evaluation for compliance

## Quick start: Store and load rules

```python
from fluxrules import F, Rule
from fluxrules.engine.phreak import PhreakEngine

# Create rules
rules = [
    Rule(
        name="high_value_transaction",
        conditions=F("amount") > 5000,
        action="require_approval",
    ),
]

# Load and evaluate with engine
engine = PhreakEngine()
engine.load_rules(rules)
result = engine.evaluate({"amount": 6000})
print(f"Matched rules: {result.fired_rules}")
```

## Persist flag

Every rule has a `persist` flag (default: `False`):

- **`persist=False`** (default) - Constructing the rule does no I/O. The rule is
  in-memory only and gets a locally generated ID.
- **`persist=True`** - The rule is written to the database during construction
  and adopts the database-assigned ID.

Constructing a `Rule` is a pure operation by default, so importing a module that
defines rules never opens a database connection. To store a rule you built
in memory, call `Rule.save()`:

```python
from fluxrules import F

rule = Rule(
    name="production_rule",
    conditions=F("x") > 10,
    action="act",
)
rule.save()  # now in the database, rule.id is the stored ID
```

`save()` is an insert, not an upsert: calling it twice stores the rule twice
and does not update an existing row. Use the repository or service layer when
you need update semantics.

```python
# Persisted rule (stored in database)
from fluxrules import F

rule1 = Rule(
    name="production_rule",
    conditions=F("x") > 10,
    action="act",
    persist=True,  # Database storage
)

# Temporary rule (in-memory only)
rule2 = Rule(
    name="test_rule",
    conditions=F("y") == "test",
    action="test_act",
    persist=False,  # No database storage
)
```

## Configuration

Set the database environment during initialization:

```python
from fluxrules.initialization import initialize_persistence

# Development (SQLite, default)
initialize_persistence(env="dev")

# Production (PostgreSQL)
initialize_persistence(env="prod", db_url="postgresql://user:pass@db.example.com/fluxrules")

# Custom URL
initialize_persistence(db_url="postgresql://localhost/my_rules")
```

**Using environment variables:**

```bash
export FLUXRULES_ENV=prod
export FLUXRULES_DB_URL=postgresql://user:pass@db.example.com/fluxrules
```

FluxRules auto-initializes the database on first use if not called explicitly.

## Audit trail

Every rule evaluation produces an audit trail automatically:

```python
from fluxrules import F, Rule
from fluxrules.engine.phreak import PhreakEngine

# Setup engine and rules
rule = Rule(name="test", conditions=F("amount") > 5000, action="flag")
engine = PhreakEngine()
engine.load_rules([rule])

fact = {"amount": 6000}
result = engine.evaluate(fact)

# Audit trail built-in to result
print(f"Matched: {result.fired_rules}")      # Rule IDs that matched
print(f"Actions: {result.actions}")          # Actions executed
print(f"Time: {result.latency_ms}ms")        # Execution time

# Log for audit
import json
audit_record = {
    "fact_id": fact.get("id"),
    "matched_rules": result.fired_rules,
    "actions": result.actions,
    "latency_ms": result.latency_ms,
}
print(json.dumps(audit_record))
```

Persist audit records to your logging backend as needed.

## Supported databases

- **SQLite** (default, development, single-file)
- **PostgreSQL** (production, scales to 100K+ rules)
- **MySQL, SQL Server, and any other SQLAlchemy-supported dialect** - via the ServiceFactory path below; see the note on `backend` in that section

---

## Using a different SQL provider (Postgres, SQL Server, etc.)

By default `persist=True` writes through the `DBConnectionManager` path, which is
configured via `initialize_persistence()` or the `FLUXRULES_DB_URL` / `FLUXRULES_ENV`
environment variables.

In real applications you typically configure a connection once at startup (e.g. in a
FastAPI lifespan handler). When you register a persistence adapter with `ServiceFactory`,
`persist=True` **automatically delegates to that adapter** instead of the default
SQLite path - no other changes needed.

### FastAPI + PostgreSQL example

```python
# python skip
from contextlib import asynccontextmanager
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from fastapi import FastAPI

from fluxrules.config import PersistenceConfig, RuntimeConfig
from fluxrules.di import ServiceFactory
from fluxrules import F, Rule

DATABASE_URL = "postgresql://user:pass@db.example.com/fluxrules"
engine = create_engine(DATABASE_URL, pool_size=10, max_overflow=20)
SessionLocal = sessionmaker(bind=engine)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Register the Postgres-backed adapter once at startup.
    ServiceFactory.create_persistence_adapter(
        session_provider=SessionLocal,
        config=RuntimeConfig(persistence=PersistenceConfig(backend="postgres")),
    )
    yield
    ServiceFactory.reset()

app = FastAPI(lifespan=lifespan)

# Anywhere in your app - persist=True now writes to Postgres, not SQLite.
rule = Rule(
    name="kyc_verified",
    domain="compliance",
    conditions=F("kyc_status") == "verified",
    action="proceed",
    persist=True,
)
```

`SQLAlchemyPersistenceAdapter` is dialect-agnostic - it works with any database
SQLAlchemy supports (PostgreSQL, MySQL, SQL Server, SQLite). The key thing to know:
`backend="postgres"` is the configuration value that activates the SQLAlchemy path
in `ServiceFactory`, regardless of the actual database dialect. Change the
`DATABASE_URL` scheme for your target database but keep `backend="postgres"`:

```python
# MySQL
DATABASE_URL = "mysql+pymysql://user:pass@db.example.com/fluxrules"

# SQL Server
DATABASE_URL = "mssql+pyodbc://user:pass@db.example.com/fluxrules?driver=ODBC+Driver+17+for+SQL+Server"
```

The rest of the setup - `session_provider`, `ServiceFactory.create_persistence_adapter()` -
is identical.

### Priority order

When `persist=True` is used, fluxrules checks in this order:

1. **ServiceFactory adapter** - if one is registered and it is not the in-memory
   fallback, it is used. This covers any SQLAlchemy-backed dialect (Postgres, MySQL,
   SQL Server) as long as `backend="postgres"` was set at registration time.
2. **DBConnectionManager** - the `initialize_persistence()` / env-var path. Used
   when no ServiceFactory adapter is registered (the common case for standalone
   scripts and simple deployments).
3. **Fallback** - if neither is reachable, a locally generated ID is assigned and
   an `INFO`-level log entry is emitted (`"No database configured; using in-memory mode"`).
   The rule is still usable in-memory.

> **Note - table creation:** `ServiceFactory` does not create database tables.
> When using the ServiceFactory path you are responsible for running schema
> migrations before the application starts (e.g. via Alembic). The
> `initialize_persistence()` helper creates tables automatically and is the
> right choice when you want a zero-config startup with SQLite or a simple
> PostgreSQL setup.

---

## Next Steps

- **Sessions** - See [Sessions](sessions.md) for stateful evaluation with persisted rulesets
- **Rule Lifecycle** - See [Rule Lifecycle](rule-lifecycle.md) for rule versioning and deletion
- **Example** - See [Example 05: Persistence](https://github.com/saurabh2mishra/fluxrules/blob/main/examples/05_persistence.py) for evaluation and audit patterns
