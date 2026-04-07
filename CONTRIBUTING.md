# Contributing to FluxRules

Thank you for considering contributing to FluxRules! This document provides guidelines and instructions for contributing.

---

## Table of Contents

- [Code of Conduct](#code-of-conduct)
- [Getting Started](#getting-started)
- [Development Setup](#development-setup)
- [Project Structure](#project-structure)
- [Making Changes](#making-changes)
- [Testing](#testing)
- [Pull Request Process](#pull-request-process)
- [Coding Standards](#coding-standards)
- [Reporting Bugs](#reporting-bugs)
- [Requesting Features](#requesting-features)

---

## Code of Conduct

By participating in this project, you agree to maintain a respectful and inclusive environment. Be kind, constructive, and professional in all interactions.

---

## Getting Started

1. **Fork** the repository on GitHub.
2. **Clone** your fork locally:
   ```bash
   git clone https://github.com/<your-username>/fluxrules.git
   cd fluxrules
   ```
3. **Create a branch** for your work:
   ```bash
   git checkout -b feature/my-feature
   ```

---

## Development Setup

### Prerequisites

- Python 3.11+
- [uv](https://docs.astral.sh/uv/) (recommended) or pip
- Redis (optional — the app falls back gracefully without it)
- Docker & Docker Compose (optional, for containerised development)

### Option A: Local Development

```bash
# 1. Copy the example env file and adjust as needed
cp .env.example backend/.env

# 2. Install dependencies
cd backend
uv sync          # or: pip install -e ".[dev]"

# 3. Run the dev server
uvicorn app.main:app --reload --port 8000

# 4. (Optional) Start Redis
redis-server

# 5. (Optional) Start the event worker
python -m app.workers.event_worker
```

### Option B: Docker

```bash
cp .env.example backend/.env
docker-compose up --build
```

The API will be at `http://localhost:8000` and the frontend at `http://localhost:8080`.

---

## Project Structure

```
fluxrules/
├── backend/
│   ├── app/
│   │   ├── api/routes/       # FastAPI route handlers
│   │   ├── analytics/        # Runtime analytics & explainability
│   │   ├── compiler/         # Rule compilation
│   │   ├── engine/           # RETE network, DSL parser, dependency graph
│   │   ├── execution/        # Agenda, scheduler, working memory
│   │   ├── models/           # SQLAlchemy ORM models
│   │   ├── schemas/          # Pydantic request/response schemas
│   │   ├── services/         # Business logic layer
│   │   ├── utils/            # Shared utilities (Redis, metrics)
│   │   ├── validation/       # BRMS validation (SAT, conflicts, gaps)
│   │   └── workers/          # Background event workers
│   ├── migrations/           # Alembic database migrations
│   ├── tests/                # Pytest test suite
│   └── simulation/           # Sample integration scripts
├── frontend/                 # Static HTML/CSS/JS frontend
├── docker-compose.yml
└── mkdocs.yml
```

---

## Making Changes

1. **Keep changes focused.** One feature or fix per pull request.
2. **Don't break existing architecture.** If you want to propose a structural change, open an issue first to discuss.
3. **Update tests.** If you add or modify backend logic, include corresponding tests.
4. **Update documentation.** If your change affects the API surface, update docstrings, the README, or MkDocs pages as appropriate.

---

## Testing

The test suite uses **pytest**. Run the full suite from the `backend/` directory:

```bash
cd backend
pytest
```

### Test conventions

- Test files live in `backend/tests/` and are named `test_*.py`.
- Use the existing `conftest.py` fixtures for database sessions and test clients.
- Aim for tests that are fast, isolated, and deterministic (no external service dependencies).

### Running a single test file

```bash
pytest tests/test_api.py
```

### Running tests matching a keyword

```bash
pytest -k "conflict"
```

---

## Pull Request Process

1. **Ensure all tests pass** locally before pushing.
2. **Write a clear PR description** explaining what changed and why.
3. **Reference related issues** (e.g., `Closes #42`).
4. **Keep the PR small.** Large PRs are harder to review.
5. A maintainer will review your PR and may request changes.
6. Once approved, your PR will be squash-merged into `main`.

---

## Coding Standards

### Python (Backend)

- **Formatter / Linter:** [Ruff](https://docs.astral.sh/ruff/) (`ruff check` and `ruff format`).
- **Type hints:** Use type annotations for all function signatures.
- **Docstrings:** Google-style docstrings for public functions and classes.
- **Imports:** Group as standard library → third-party → local, separated by blank lines.

### JavaScript (Frontend)

- Vanilla JS (no build step required).
- Use the existing `showToast()` utility for user-facing messages instead of `alert()`.
- Keep code in focused modules under `frontend/js/`.

### Commits

- Use clear, concise commit messages.
- Prefix with a category when helpful: `fix:`, `feat:`, `docs:`, `test:`, `chore:`.

---

## Reporting Bugs

Open a GitHub Issue with:

1. **Summary** — A clear, one-line description.
2. **Steps to reproduce** — Minimal steps to trigger the bug.
3. **Expected behaviour** — What you expected to happen.
4. **Actual behaviour** — What actually happened (include error messages / stack traces).
5. **Environment** — Python version, OS, Docker or local, browser (if frontend).

---

## Requesting Features

Open a GitHub Issue labelled `enhancement` with:

1. **Problem statement** — What are you trying to do?
2. **Proposed solution** — How do you think it should work?
3. **Alternatives considered** — Any other approaches you thought of.

---

## License

By contributing to FluxRules, you agree that your contributions will be licensed under the [MIT License](LICENSE).
