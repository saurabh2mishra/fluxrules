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

- `GET /health`: Health check
- `POST /api/v1/rules`: Store a rule (rules live in the server's database)
- `POST /api/v1/evaluate`: Evaluate one fact against the stored rules
- `POST /api/v1/evaluate/bulk`: Evaluate several facts in one request
- `GET /api/v1/explain/{execution_id}`: Look up an earlier evaluation
- `POST /api/v1/rules/simulate`: Dry run with an explanation per matched rule
- `POST /validate`: Check a rule set without storing it

All of them except `/health` and `/validate` need a login token. See
[Logging in](../rest-api.md#logging-in).

## Evaluate Request

```json
POST /api/v1/evaluate
{
  "facts": {"amount": 2500, "country": "US"},
  "ruleset_id": "payments"
}
```

`ruleset_id` is optional and picks the rules of one `group`.

Response:

```json
{
  "execution_id": "8ac723da-c93d-40ec-809c-64a244003e9e",
  "ruleset_group": "payments",
  "matched_rules": [1, 3],
  "actions": ["flag", "review"],
  "facts": {"amount": 2500, "country": "US"}
}
```

---

## Next Steps

- **Full API Reference**: See [REST API](../rest-api.md)
- **Deployment**: See [Deployment](../deployment.md)
