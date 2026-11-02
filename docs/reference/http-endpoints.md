# HTTP Endpoints Reference

Quick reference for all REST endpoints.

## Core Endpoints

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/health` | Health check |
| POST | `/api/v1/auth/token` | Log in and get a token |
| POST | `/api/v1/rules` | Store a rule |
| GET | `/api/v1/rules` | List stored rules |
| POST | `/api/v1/evaluate` | Evaluate one fact against stored rules |
| POST | `/api/v1/evaluate/bulk` | Evaluate several facts |
| GET | `/api/v1/explain/{execution_id}` | Look up an earlier evaluation |
| POST | `/api/v1/rules/simulate` | Dry run with explanations |
| POST | `/validate` | Check a rule set without storing it |
| POST | `/api/v1/sessions` | Create a session that stores facts |
| POST | `/api/v1/sessions/{id}/evaluate` | Evaluate each fact stored in a session |
| POST | `/api/v1/engines/evaluate` | Evaluate a fact, with an explanation per matched rule |

## Setup

```bash
pip install 'fluxrules[api]'
uvicorn fluxrules.api.app:create_app --factory
```

See [REST API](../rest-api.md) for complete documentation.
