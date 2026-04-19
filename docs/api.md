# API Contract

Stable endpoints are exposed under `/v1`.

- `POST /v1/rulesets/{ruleset_id}/evaluate`
- `POST /v1/rulesets/{ruleset_id}/simulate`
- `GET /v1/rulesets/{ruleset_id}/validate`
- `GET /v1/executions/{execution_id}`
- `GET /v1/health`

Compatibility rule: `/v1` keeps backward-compatible schema changes only.
