# FluxRules

A business rule engine powered by the RETE algorithm, with built-in conflict detection, versioning, and a visual management UI.

---

## Architecture

```
┌──────────────────────────┐        ┌──────────────────────────┐
│ External Application(s)  │        │ FluxRules Frontend (UI)  │
│ - backend services       │        │ - Rule builder           │
│ - workflows / cron jobs  │        │ - Conflict viewer        │
│                          │        │ - Metrics dashboard      │
└──────────────┬───────────┘        └──────────────┬───────────┘
               │ REST + JWT                        │ REST + JWT
               └────────────────────┬──────────────┘
                                    ▼
                     ┌──────────────────────────────────────┐
                     │        FastAPI Backend (/api/v1)     │
                     │                                      │
                     │  Integration endpoints:              │
                     │  - POST /auth/token                  │
                     │  - POST /event                       │
                     │  - CRUD /rules (+ /validate)         │
                     │  - /analytics, /metrics, /graph      │
                     └───────────────┬──────────────────────┘
                                     │
        ┌────────────────────────────┼────────────────────────────┐
        ▼                            ▼                            ▼
┌───────────────┐           ┌──────────────────┐          ┌───────────────┐
│ BRMS Validate │           │ RETE Execution   │          │ Analytics     │
│ conflict/dead │           │ agenda/scheduler │          │ coverage/expl │
│ sat/gap/dup   │           │ working memory   │          │ runtime stats │
└──────┬────────┘           └────────┬─────────┘          └──────┬────────┘
       └───────────────────────┬─────┴───────────────────────────┘
                               ▼
                     ┌───────────────────────────┐
                     │ Storage & Infra           │
                     │ SQLite/Postgres + Redis   │
                     │ (worker optional)         │
                     └───────────────────────────┘
```

### Integration flow (for external applications)

1. Authenticate via `POST /api/v1/auth/token` and store bearer token.
2. Manage rules via `/api/v1/rules` (optionally pre-check with `/api/v1/rules/validate`).
3. Send facts/events to `POST /api/v1/event` for runtime evaluation.
4. Read outcomes and observability from `/api/v1/analytics/*` and `/api/v1/metrics`.

**Key components:**

| Layer | What it does |
|---|---|
| **RETE Network** | Alpha nodes test individual conditions; beta nodes join across rules — gives O(1) incremental matching |
| **DSL Parser** | Translates JSON condition trees (AND/OR, 14 operators) into RETE nodes |
| **BRMS Validation** | SAT-solver-backed conflict, dead-rule, gap, redundancy, and duplicate detection |
| **Execution** | Priority-ordered agenda, working memory, and a scheduler for async event processing (`POST /api/v1/event`) |
| **Versioning** | Every rule edit creates an immutable version with full diff support |

---


## Analytics & Explainability

FluxRules now exposes a unified analytics layer for runtime observability and explainability:

- `GET /api/v1/analytics/runtime` → summary, hot/cold rules, recent explanations
- `GET /api/v1/analytics/rules/top?limit=10` → top-fired and never-fired rules
- `GET /api/v1/analytics/rules/{rule_id}` → per-rule runtime detail and explanation feed
- `GET /api/v1/analytics/explanations?rule_id=&limit=` → explainability event stream
- `GET /api/v1/analytics/coverage` → coverage-focused view

### Sample runtime payload

```json
{
  "summary": {
    "total_rules": 20,
    "triggered_rules": 12,
    "coverage_pct": 60.0,
    "rules_never_fired_count": 8,
    "events_processed": 300,
    "rules_fired": 940,
    "avg_processing_time_ms": 4.82
  },
  "top_hot_rules": [],
  "cold_rules": [],
  "recent_explanations": []
}
```

Operational notes:

- Redis is optional. If unavailable, analytics automatically fall back to in-memory storage and events are processed synchronously via API fallback.
- Postgres is optional. If `DATABASE_URL` points to an unavailable Postgres instance, FluxRules automatically falls back to local SQLite (`rule_engine.db`).
- Explanation history is bounded (rolling window) to avoid unbounded memory growth.

---

## Quick Start

### With Docker (recommended)

```bash
docker-compose up --build
```

- **App** → [http://localhost:8000](http://localhost:8000)
- **API docs** → [http://localhost:8000/docs](http://localhost:8000/docs)

### Without Docker

```bash
# 1. Start Redis (optional — the app falls back gracefully)
redis-server

# 2. Install dependencies & run
cd backend
uv sync                   
uvicorn app.main:app --reload --port 8000

# 3. (Optional) Start the event worker
python -m app.workers.event_worker
```

Open [http://localhost:8000](http://localhost:8000) — the frontend is served by FastAPI directly.


### Sample integration app (event execution)

A ready-to-run sample client is available at `backend/simulation/sample_event_app.py`. It demonstrates:

- registering/logging in,
- creating a sample rule,
- validating match behavior with `/api/v1/rules/simulate`,
- executing the event via `POST /api/v1/event`,
- and reading runtime analytics.

```bash
cd backend
python simulation/sample_event_app.py --base-url http://localhost:8000/api/v1
```

### Run tests

```bash
cd backend
pytest
```
