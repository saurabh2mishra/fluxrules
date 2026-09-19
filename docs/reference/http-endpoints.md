# HTTP Endpoints Reference

Quick reference for all REST endpoints.

## Core Endpoints

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/health` | Health check |
| POST | `/api/v1/evaluate` | Evaluate facts against rules |
| POST | `/api/v1/validate` | Validate DSL or ruleset |
| GET | `/api/v1/executions/{id}` | Get execution details |

## Setup

```bash
pip install 'fluxrules[api]'
uvicorn fluxrules.api.app:create_app --factory
```

See [REST API](../rest-api.md) for complete documentation.
