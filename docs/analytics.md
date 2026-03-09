# FluxRules Analytics

## Data model

Unified analytics contracts are in `backend/app/schemas/analytics.py`:

- `RuntimeAnalyticsSummary`
- `RuleRuntimeMetric`
- `RuleExplainabilityEntry`
- `TopRulesResponse`
- `RuntimeAnalyticsResponse`
- `AnalyticsCoverageResponse`

## Ingestion flow

1. Event worker pops an event from queue.
2. Engine evaluates event and returns matched rules + explanations.
3. Worker records:
   - event processing time
   - rule execution metrics
   - explanation artifacts
4. Metrics are persisted via `AnalyticsStore` abstraction:
   - Redis-backed store if Redis is available
   - in-memory fallback otherwise

If Redis is unavailable, event submission falls back to synchronous processing in API so local development remains dependency-light.

## API endpoints

- `GET /api/v1/analytics/runtime`
- `GET /api/v1/analytics/rules/top?limit=10`
- `GET /api/v1/analytics/rules/{rule_id}`
- `GET /api/v1/analytics/explanations?rule_id=&limit=`
- `GET /api/v1/analytics/coverage`

## UI mapping

`frontend/js/metrics-viewer.js` uses analytics APIs to render:

- runtime summary cards
- top hot rules table
- cold rules table
- recent explainability feed
- clickable rule drilldown modal

## Extension points

- Persist time-series rollups for daily/weekly trend charts.
- Add tenant/workspace dimensions for multi-tenant analytics.
- Emit analytics events to external observability pipelines.
