# REST API

**Prerequisites:** [Concepts](concepts.md) (Rule, Engine).

---

FluxRules exposes a REST API for evaluating rules from other services. The API is built with FastAPI and all endpoints are under `/api/v1`.

## Starting the API server

Install the `api` extra, then start the server from the command line:

```bash
pip install "fluxrules[api]"
fluxrules serve --port 8000
```

Or start it from Python:

```python
from fluxrules.api.app import create_app
import uvicorn

app = create_app()

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
```

While it runs, `http://localhost:8000/docs` lists every endpoint and lets you
try them.

## Core endpoints

Most endpoints need a login token. [REST API](rest-api.md#logging-in) shows
how to get one, and gives the full request and response of each endpoint.

### Health check

```bash
GET /health
```

Answers `{"status": "healthy"}`. No login needed.

### Store a rule

```bash
POST /api/v1/rules
Content-Type: application/json

{
  "name": "big_payment",
  "group": "payments",
  "action": "review",
  "conditions": {"type": "condition", "field": "amount", "op": ">", "value": 1000}
}
```

Rules live in the server's database. Store them before you evaluate.

### Evaluate a fact

```bash
POST /api/v1/evaluate
Content-Type: application/json

{
  "facts": {"amount": 4200, "country": "DE"},
  "ruleset_id": "payments"
}
```

`ruleset_id` is optional and picks the rules of one `group`. Without it, all
stored rules are used.

**Response:**
```json
{
  "execution_id": "8ac723da-c93d-40ec-809c-64a244003e9e",
  "ruleset_group": "payments",
  "matched_rules": [1],
  "actions": ["review"],
  "facts": {"amount": 4200, "country": "DE"}
}
```

`POST /api/v1/evaluate/bulk` takes a list under `facts` and returns one result
per fact.

### Look up an evaluation

```bash
GET /api/v1/explain/{execution_id}
```

Returns an earlier evaluation by the `execution_id` it answered with.

### Dry run with explanations

```bash
POST /api/v1/rules/simulate
Content-Type: application/json

{"event": {"amount": 4200, "country": "DE"}}
```

Returns the matched rules in firing order, with an explanation for each.

### Check a rule set

```bash
POST /validate
Content-Type: application/json

{"ruleset": {"group": "payments", "rules": [...]}}
```

Answers `{"issues": [...]}`, a list of problems found; an empty list means the
rule set is fine. No login needed.

## More endpoints

- **Rules** (`/api/v1/rules`): list, update, delete, versions and conflict
  checks.
- **Sessions** (`/api/v1/sessions`): store facts under a session id.
- **Audit** (`/api/v1/audit`): the audit trail of rule changes.
- **Metrics** (`/api/v1/metrics`): Prometheus metrics.

## API versioning

All endpoints are under `/api/v1` for stability. Breaking changes will use `/api/v2`.

---

## Next Steps

- **REST API Detailed**: See [REST API](rest-api.md) for full endpoint reference
- **Example**: See [Example 12: API Usage](https://github.com/saurabh2mishra/fluxrules/blob/main/examples/12_api_usage.py) for working client code
- **Deployment**: See [Deployment](deployment.md) for production setup
