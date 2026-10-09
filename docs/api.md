# REST API

**Prerequisites:** [Concepts](concepts.md) (Rule, Engine).

---

FluxRules exposes a REST API for evaluating rules from other services. The API is built with FastAPI and all endpoints are under `/api/v1`.

## Starting the API server

```python
from fluxrules.api.app import create_app
import uvicorn

app = create_app()

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
```

Or run from CLI:

```bash
python -m fluxrules.api.app
```

## Core endpoints

### Health check

```bash
GET /health
```

Returns server status.

### Evaluate rules

```bash
POST /api/v1/evaluate
Content-Type: application/json

{
  "facts": {"amount": 5000, "country": "US"},
  "domain": "fraud_detection"
}
```

**Response:**
```json
{
  "fired_rules": [1, 3],
  "actions": ["flag_for_review"],
  "latency_ms": 2.5
}
```

### Simulate rule changes

```bash
POST /api/v1/simulate
Content-Type: application/json

{
  "facts": {"amount": 5000, "country": "US"},
  "domain": "fraud_detection"
}
```

Returns potential matches if rules are changed.

### Validate DSL

```bash
POST /api/v1/validate
Content-Type: application/json

{
  "condition_dsl": {
    "type": "condition",
    "field": "amount",
    "op": ">",
    "value": 5000
  }
}
```

**Response:**
```json
{
  "valid": true,
  "errors": []
}
```

### Explain rule match

```bash
POST /api/v1/explain
Content-Type: application/json

{
  "rule_id": 1,
  "facts": {"amount": 5000}
}
```

Returns why/why-not a rule matched.

## Optional endpoints

Additional endpoints are available if extras are installed:

- **Rules management** (`/api/v1/rules`) - CRUD operations (requires `[sql]`)
- **Sessions** (`/api/v1/sessions`) - Stateful evaluation (requires `[sql]`)
- **Audit logging** (`/api/v1/audit`) - Audit trail (requires `[sql]`)
- **Metrics** (`/api/v1/metrics`) - Prometheus metrics (requires `[otel]`)

## API versioning

All endpoints are under `/api/v1` for stability. Breaking changes will use `/api/v2`.

---

## Next Steps

- **REST API Detailed** - See [REST API](rest-api.md) for full endpoint reference
- **Example** - See [Example 12: API Usage](https://github.com/fluxrules/fluxrules/blob/main/examples/12_api_usage.py) for working client code
- **Deployment** - See [Deployment](deployment.md) for production setup
