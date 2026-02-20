# RETE Rules Engine

A high-performance rule management and execution platform using the RETE algorithm. Built with FastAPI and have a modern but userfriendly UI.

## Features

### Rule Engine
- **True RETE Algorithm** - O(1) pattern matching with alpha/beta networks
- **Nested Conditions** - Unlimited depth AND/OR condition trees
- **14 Operators** - `==`, `!=`, `>`, `<`, `>=`, `<=`, `in`, `not_in`, `contains`, `starts_with`, `ends_with`, `regex`, `exists`, `not_exists`
- **Priority Execution** - Rules execute in priority order within groups
- **Action Registry** - Pluggable action functions (flag, block, alert, etc.)
- **Hot Reload** - Update rules without restart

### Conflict Detection
- **Duplicate Conditions** - Finds rules with identical logic
- **Priority Collisions** - Same priority in same group
- **Real-time Validation** - Check conflicts before saving

### Rule Management
- **Version History** - Full audit trail with diff view
- **Rule Groups** - Organize by category (fraud, compliance, etc.)
- **Bulk Operations** - Create/import multiple rules at once
- **Dependency Graph** - Visualize rule relationships

### Performance
- **~2ms per rule creation** - Optimized DB transactions
- **~4ms conflict detection** - Hash-based comparison
- **Local + Redis caching** - Graceful fallback when Redis unavailable
- **SQLite WAL mode** - Fast concurrent writes

### Frontend
- **Deep Ocean Theme** - Modern dark/light mode
- **Stepper Wizard** - 4-step rule creation flow
- **Live Filtering** - Search rules by name, group, status
- **Expandable Cards** - Clean rule list with details on demand
- **Toast Notifications** - Non-blocking feedback
- **Syntax Highlighting** - JSON condition preview

## Tech Stack

| Component | Technology |
|-----------|------------|
| Backend | Python 3.11, FastAPI, SQLAlchemy, Pydantic |
| Frontend | Vanilla JS, CSS Variables, D3.js |
| Database | SQLite (dev), PostgreSQL (prod) |
| Cache | Redis (optional) |
| Metrics | Prometheus |

## Quick Start

### Using uv (Recommended)
```bash
cd backend
uv sync
uv run uvicorn app.main:app --reload --port 8000

# Frontend (separate terminal)
cd frontend
python -m http.server 8080
```

### Using Docker
```bash
docker-compose up --build
```

### Access
- **Frontend:** http://localhost:8080
- **API Docs:** http://localhost:8000/docs
- **Login:** `admin` / `admin123`

## API Reference

### Authentication
```
POST /api/v1/auth/token        # Login (form data)
POST /api/v1/auth/register     # Register user
```

### Rules
```
GET    /api/v1/rules                    # List all rules
POST   /api/v1/rules                    # Create rule
POST   /api/v1/rules?skip_conflict_check=true  # Fast create (no validation)
POST   /api/v1/rules/bulk               # Bulk create
GET    /api/v1/rules/{id}               # Get rule
PUT    /api/v1/rules/{id}               # Update rule
DELETE /api/v1/rules/{id}               # Delete rule
POST   /api/v1/rules/validate           # Validate before save
POST   /api/v1/rules/simulate           # Test rule against event
```

### Versioning
```
GET /api/v1/rules/{id}/versions              # List versions
GET /api/v1/rules/{id}/versions/{version}    # Get specific version
GET /api/v1/rules/{id}/diff/{v1}/{v2}        # Compare versions
```

### Engine
```
POST /api/v1/rules/reload              # Hot reload rules
GET  /api/v1/rules/engine/stats        # Engine statistics
POST /api/v1/rules/engine/invalidate-cache  # Clear cache
GET  /api/v1/rules/graph/dependencies  # Dependency graph
GET  /api/v1/rules/conflicts/detect    # Find all conflicts
GET  /api/v1/rules/actions/available   # List action functions
```

### Events
```
POST /api/v1/events    # Submit event for processing (requires Redis)
```

## Rule Structure

```json
{
  "name": "High Value US Transaction",
  "description": "Flag large transactions from US",
  "group": "fraud_detection",
  "priority": 10,
  "enabled": true,
  "condition_dsl": {
    "type": "group",
    "op": "AND",
    "children": [
      {"type": "condition", "field": "amount", "op": ">", "value": 10000},
      {"type": "condition", "field": "country", "op": "==", "value": "US"}
    ]
  },
  "action": "flag_suspicious"
}
```

## Testing

```bash
cd backend

# Run all tests
uv run pytest

# Run with coverage
uv run pytest --cov=app

# Performance test
uv run python test_performance.py
```

## Project Structure

```
backend/
├── app/
│   ├── api/routes/       # API endpoints
│   ├── engine/           # RETE implementation
│   │   ├── rete_network.py      # Core RETE algorithm
│   │   ├── optimized_rete_engine.py  # Caching layer
│   │   ├── actions.py           # Action registry
│   │   └── dependency_graph.py  # Rule relationships
│   ├── models/           # SQLAlchemy models
│   ├── schemas/          # Pydantic schemas
│   ├── services/         # Business logic
│   └── utils/            # Redis, metrics
├── tests/                # pytest tests
└── test_performance.py   # Benchmark script

frontend/
├── index.html            # Main dashboard
├── login.html            # Auth page
├── css/style.css         # Deep Ocean theme
└── js/
    ├── app.js            # Router & init
    ├── rule-builder.js   # Stepper wizard
    ├── rule-list.js      # List & filters
    └── ...
```

## License

MIT
