# REST API Reference

**Prerequisites:** [API](api.md) (core endpoints).

---

Comprehensive reference for all REST API endpoints.

## Request/Response Format

All requests use `Content-Type: application/json`.

All responses include:
- `fired_rules` — List of matched rule IDs
- `actions` — List of triggered actions
- `latency_ms` — Evaluation time in milliseconds

## Endpoints

### POST /api/v1/evaluate

Evaluate facts against rules.

**Request:**
```json
{
  "facts": {
    "amount": 5000,
    "country": "US",
    "ip_risk_score": 45
  },
  "domain": "fraud_detection"
}
```

**Response:**
```json
{
  "fired_rules": [1, 2],
  "actions": ["flag_for_review", "notify_analyst"],
  "latency_ms": 2.1
}
```

### POST /api/v1/evaluate/bulk

Evaluate multiple facts in batch.

**Request:**
```json
{
  "facts": [
    {"amount": 1000, "country": "US"},
    {"amount": 50000, "country": "NG"}
  ],
  "domain": "fraud_detection"
}
```

**Response:**
```json
{
  "results": [
    {"fired_rules": [1], "actions": ["proceed"], "latency_ms": 1.2},
    {"fired_rules": [1, 3], "actions": ["block"], "latency_ms": 1.5}
  ]
}
```

### POST /api/v1/explain

Get detailed explanation of rule matching.

**Request:**
```json
{
  "rule_id": 1,
  "facts": {"amount": 7500, "country": "NG"}
}
```

**Response:**
```json
{
  "rule_id": 1,
  "rule_name": "high_value_transaction",
  "condition_dsl": {...},
  "matched": true,
  "matching_conditions": ["amount > 5000"],
  "explanation": "Amount exceeds threshold"
}
```

### POST /api/v1/simulate

Simulate rule changes without persisting.

**Request:**
```json
{
  "rules": [
    {
      "name": "test_rule",
      "condition_dsl": {...},
      "action": "flag"
    }
  ],
  "facts": {"amount": 5000}
}
```

**Response:**
```json
{
  "fired_rules": [999],
  "actions": ["flag"],
  "latency_ms": 1.8
}
```

### POST /api/v1/validate

Validate DSL syntax.

**Request:**
```json
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

### GET /health

Health check endpoint.

**Response:**
```json
{
  "status": "healthy",
  "version": "0.1.0"
}
```

## Optional Endpoints (with extras)

### POST /api/v1/rules (requires [sql])

Create a new rule.

**Request:**
```json
{
  "name": "new_rule",
  "domain": "fraud_detection",
  "condition_dsl": {...},
  "action": "flag"
}
```

### GET /api/v1/rules (requires [sql])

List all rules.

### POST /api/v1/sessions (requires [sql])

Create a new evaluation session.

**Request:**
```json
{
  "ruleset_id": 1
}
```

### POST /api/v1/sessions/{id}/facts (requires [sql])

Add facts to a session.

**Request:**
```json
{
  "fact_id": "txn_123",
  "event": {"amount": 5000, "country": "US"}
}
```

## Error Responses

All errors follow this format:

```json
{
  "detail": "Error message",
  "error_code": "VALIDATION_ERROR"
}
```

Common error codes:
- `VALIDATION_ERROR` — Invalid request format
- `DSL_ERROR` — Invalid DSL syntax
- `RULE_NOT_FOUND` — Rule ID does not exist
- `INTERNAL_ERROR` — Server error

---

## Next Steps

- **API Overview** — See [API](api.md) for quick start
- **Example** — See [Example 12: API Usage](https://github.com/fluxrules/fluxrules/blob/main/examples/12_api_usage.py) for working client code
