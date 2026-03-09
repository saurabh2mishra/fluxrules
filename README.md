# FluxRules

A business rule engine powered by the RETE algorithm, with built-in conflict detection, versioning, and a visual management UI.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                        Frontend                             │              │
│   (Rule Builder, Dependency Graph, Metrics, Test Sandbox)   │
└──────────────────────────┬──────────────────────────────────┘
                           │ REST
┌──────────────────────────▼──────────────────────────────────┐
│                     FastAPI Backend                         │
│                                                             │
│  API Routes          Services            Engine             │
│  ┌──────────┐   ┌────────────────┐   ┌────────────────┐     │
│  │ /rules   │──▶│ Rule Service   │──▶│ RETE Network   │     │
│  │ /events  │   │ Auth Service   │   │ Alpha / Beta   │     │
│  │ /metrics │   │ Audit Service  │   │ DSL Parser     │     │
│  │ /auth    │   │ BRMS Service   │   │ Action Registry│     │
│  │ /graph   │   └────────────────┘   └────────────────┘     │
│  └──────────┘                                               │  
│                                                             │
│  Validation Layer         Execution          Analytics      │
│  ┌──────────────────┐   ┌──────────────┐  ┌────────────┐    │
│  │ Conflict Detect.  │   │ Scheduler    │  │ Coverage   │   │
│  │ Dead Rule Detect. │   │ Agenda       │  │ Metrics    │   │
│  │ SAT Validation    │   │ Working Mem. │  │ Explanations│  │
│  │ Gap / Redundancy  │   └──────────────┘  └────────────┘   │
│  │ Duplicate / Prio. │                                      │
│  └──────────────────┘                                       │
│                                                             │
│  Workers                 Storage                            │
│  ┌──────────────┐   ┌──────────────────────────┐            │
│  │ Event Worker  │   │ SQLite (dev) / Postgres  │           │
│  └──────────────┘   │ Redis (cache, optional)   │           │
│                      └──────────────────────────┘           │
└─────────────────────────────────────────────────────────────┘
```

**Key components:**

| Layer | What it does |
|---|---|
| **RETE Network** | Alpha nodes test individual conditions; beta nodes join across rules — gives O(1) incremental matching |
| **DSL Parser** | Translates JSON condition trees (AND/OR, 14 operators) into RETE nodes |
| **BRMS Validation** | SAT-solver-backed conflict, dead-rule, gap, redundancy, and duplicate detection |
| **Execution** | Priority-ordered agenda, working memory, and a scheduler for async event processing |
| **Versioning** | Every rule edit creates an immutable version with full diff support |

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

### Run tests

```bash
cd backend
pytest
```
