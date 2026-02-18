# README.md

# RETE Rule Engine Platform

Production-ready rule management and execution platform using the RETE algorithm.

## Features

- Rule CRUD operations with versioning
- Nested AND/OR conditions (unlimited depth)
- Priority-based rule execution
- Hot reload without restart
- Conflict detection
- Dependency visualization
- Event simulation
- Role-based access control (Admin/Business)
- Distributed worker processing
- Prometheus metrics

## Tech Stack

**Backend:** Python 3.11, FastAPI, SQLAlchemy, durable_rules, Redis, Prometheus  
**Frontend:** HTML, CSS, Vanilla JavaScript, D3.js  
**Infra:** Docker, docker-compose

## Quick Start

### With Docker
```bash
docker-compose up --build
```

Access:
- Frontend: http://localhost:8080
- API: http://localhost:8000
- API Docs: http://localhost:8000/docs
- Metrics: http://localhost:8000/api/v1/metrics

### Without Docker
```bash
chmod +x setup.sh
./setup.sh

# Terminal 1: API
cd backend
source venv/bin/activate
uvicorn app.main:app --reload

# Terminal 2: Worker
cd backend
source venv/bin/activate
python -m app.workers.event_worker

# Terminal 3: Redis
redis-server

# Terminal 4: Frontend
cd frontend
python -m http.server 8080
```

## Default Credentials

- Username: `admin`
- Password: `admin123`

## Testing
```bash
cd backend
source venv/bin/activate
pytest
```

## API Endpoints

- `POST /api/v1/auth/token` - Login
- `POST /api/v1/auth/register` - Register
- `GET /api/v1/rules` - List rules
- `POST /api/v1/rules` - Create rule
- `PUT /api/v1/rules/{id}` - Update rule
- `DELETE /api/v1/rules/{id}` - Delete rule
- `GET /api/v1/rules/{id}/versions` - Get versions
- `GET /api/v1/rules/{id}/diff/{v1}/{v2}` - Version diff
- `POST /api/v1/rules/simulate` - Simulate event
- `POST /api/v1/rules/reload` - Hot reload
- `GET /api/v1/rules/graph/dependencies` - Dependency graph
- `GET /api/v1/rules/conflicts/detect` - Detect conflicts
- `POST /api/v1/events` - Submit event
- `GET /api/v1/metrics` - Prometheus metrics

## License

MIT