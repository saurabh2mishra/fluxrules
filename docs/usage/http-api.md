# HTTP API

**Prerequisites:** [API Overview](../api.md), [REST API Reference](../rest-api.md).

---

FluxRules provides a REST API for rule evaluation via HTTP.

## Setup

Install API dependencies:

```bash
pip install 'fluxrules[api]'
```

Start the server:

```bash
uvicorn fluxrules.api.app:create_app --factory --host 0.0.0.0 --port 8000
```

## Core Endpoints

The API includes these core routes:

- `GET /health` — Health check
- `POST /api/v1/evaluate` — Evaluate facts against rules
- `POST /api/v1/validate` — Validate DSL or ruleset
- `GET /api/v1/executions/{id}` — Get execution details
- `POST /api/v1/simulate` — Simulate rule with custom facts

## Evaluate Request

```json
POST /api/v1/evaluate
{
  "ruleset": {...},
  "facts": {"amount": 2500, "country": "US"}
}
```

Response:

```json
{
  "fired_rules": [1, 3],
  "actions": ["flag", "review"],
  "latency_ms": 2.5,
  "execution_id": "exec-123"
}
```

---

## Next Steps

- **Full API Reference** — See [REST API](../rest-api.md)
- **Deployment** — See [Deployment](../deployment.md)
    ]
  },
  "facts": {"age": 30}
}
```
