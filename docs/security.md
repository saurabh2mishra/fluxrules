# Security

**Prerequisites:** [API](api.md) and [Deployment](deployment.md).

---

Security considerations for running FluxRules in production.

## Authentication (API)

By default, the API has no authentication. Add it for production:

```python
# python skip
from fastapi import Depends, FastAPI, HTTPException
from fastapi.security import HTTPBearer

app = FastAPI()
security = HTTPBearer()


@app.post("/api/v1/evaluate")
async def evaluate(request: EvaluateRequest, credentials=Depends(security)):
    """Endpoint requiring valid bearer token."""
    token = credentials.credentials
    if not validate_token(token):
        raise HTTPException(status_code=401)

    # Proceed with evaluation
    return engine.evaluate(request.facts)
```

For production, use OAuth2 or API keys via a gateway (nginx, AWS API Gateway, etc.).

## Input validation

All facts are validated before evaluation:

```python
# python skip
from fluxrules.domain.dsl.validation import validate_dsl, DSLValidationError
from fastapi import HTTPException

# Validate rule DSL before accepting from API
try:
    validate_dsl(rule.condition_dsl)
except DSLValidationError as e:
    raise HTTPException(status_code=400, detail=str(e))
```

## Database security

If using persistence, secure the database:

```bash
# Use SSL for database connections
export DATABASE_URL="postgresql://user:pass@db.example.com/fluxrules?sslmode=require"

# Restrict database access to app instances only
# Use VPC/security groups to isolate database
```

## Audit logging

Track all rule changes and evaluations:

```python
# Enable audit trail (requires [sql])
from fluxrules.initialization import initialize_persistence

initialize_persistence(env="prod")  # Enables audit logging
```

Check audit logs:

```bash
# Via REST API (if available)
curl http://localhost:8000/api/v1/audit?limit=100
```

## Secrets management

Use environment variables for secrets, never hardcode:

```python
import os

db_url = os.getenv("DATABASE_URL")  # From environment
api_key = os.getenv("API_KEY")  # From secret store

# Never do this:
# db_url = "postgresql://user:password@db.example.com/db"
```

---

## Threat model

A short, honest model of the surfaces an operator is responsible for. FluxRules
is a library plus an optional HTTP service; most controls are the operator's to
apply.

### Trust boundaries

| Boundary | Who is trusted | Primary risk |
|----------|----------------|--------------|
| **Rule authors** | Whoever can create/modify rules | A malicious or buggy rule can match/act incorrectly; custom operators/actions/engines run arbitrary Python in-process |
| **Fact producers** | Callers of `evaluate()` / the HTTP API | Malformed or oversized facts; injection into downstream actions |
| **HTTP clients** | API consumers | Unauthenticated access, DoS via large payloads/rulesets |
| **Persistence** | The database | Tampered rules loaded from storage; connection credentials |

### Assets

- Rule definitions and their execution results/audit trail.
- The evaluation process (availability and correctness).
- Persistence credentials and the API `SECRET_KEY`.

### Threats and mitigations

| Threat | Mitigation in FluxRules | Operator responsibility |
|--------|-------------------------|-------------------------|
| Arbitrary code via custom operators/actions/engines | Extension registration is explicit; entry-point discovery is opt-in (never an import side effect) | Only load trusted plugins; review `load_plugins()` sources |
| Malicious rule DSL | `validate_dsl` / `ValidationService` reject malformed logic; the engine evaluates data, not `eval` | Validate rules at the API boundary before persisting |
| SQL injection | ORM + parameterized queries; internal DDL uses constant table names (bandit/ruff-gated) | Use least-privilege DB accounts |
| Unauthenticated API access | Auth primitives shipped (`bcrypt`, `python-jose`) | Enforce auth + network restrictions (no auth by default) |
| Tampered stored rules | Audit trail with integrity hashing | Restrict who can write to the rule store |
| Supply-chain compromise | Pinned dev tooling, Dependabot, CI `security` job (bandit + pip-audit), signed releases + SBOM | Verify release signatures/SBOM before deploying |
| Denial of service | Working-memory high-water mark; bounded evaluation | Rate-limit and size-limit inputs at the gateway |

### Out of scope

FluxRules does not sandbox custom Python extensions, does not provide
authentication middleware by default, and does not manage secrets — these are
delegated to the deployment environment and the guidance above.

## Dependency advisory triage

The optional `api` extra is the only dependency path that currently resolves the
known Starlette advisories reported by `pip-audit` in this repository. The core
package itself depends only on `pydantic`, so the risk is limited to installs
that include the API stack.

| Dependency path | Observed report | Current status | Rationale |
|---|---|---|---|
| `fluxrules[api]` -> `fastapi==0.115.14` -> `starlette==0.46.2` | Multiple Starlette advisories (including `PYSEC-2026-1941`, `PYSEC-2026-1942`, `PYSEC-2026-2280`, `PYSEC-2026-2281`, `PYSEC-2026-248`, `PYSEC-2026-249`) | Under triage / not yet remediated in the project | The FastAPI cap in `pyproject.toml` is intentional: `fastapi>=0.115,<0.116` avoids the route-introspection break that appears in Starlette 1.x/FastAPI 0.116+ behavior. Upgrading the stack without adjusting route registration semantics would change API behavior and is not a safe default fix. |
| `fluxrules[api]` -> `python-jose[cryptography]` -> `ecdsa==0.19.2` | `ecdsa` advisory (`PYSEC-2026-1325`) | Under triage / no direct remediation yet in the supported constraint set | The package is used via the auth stack. The project does not currently specify a safe replacement or a compatible patched version within the app's constraints. |
| Core install (`fluxrules`) | No direct advisories from the project package metadata | Not currently blocked for core-only consumers | The core library does not pull in the vulnerable API/web stack by default. |

This is a recorded exception, not a silent suppression: the repository keeps the
scan visible in CI, and the project is not claiming that the API extra is free of
known issues. The current maintainer posture is to keep the API extra under a
compatibility guard until a version set is proven to preserve the existing route
registration and authentication behavior. If a compatible upgrade path becomes
available, it should be validated with the API integration tests before being
accepted as a dependency change.

---

## Next Steps

- **Deployment** — See [Deployment](deployment.md) for production setup
- **Observability** — See [Observability](observability.md) for monitoring
