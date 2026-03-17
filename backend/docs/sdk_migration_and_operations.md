# SDK Migration and Server Operations Guide

## 1) Installation after migration

Use either package manager:

```bash
pip install fluxrules
```

```bash
uv add fluxrules
```

## 2) Running the server (API-only mode)

To decouple backend runtime from frontend assets, disable static mount:

```bash
export SERVE_FRONTEND=false
cd backend
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

## 3) Running the server (integrated mode)

```bash
export SERVE_FRONTEND=true
cd backend
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

## 4) Validation workflow at scale

- Request-time rule writes use candidate validation (fast path).
- Full all-vs-all validation should run asynchronously (batch/admin/scheduled).
- Keep SAT/redundancy/gap checks out of synchronous write-path for large rulesets.

## 5) Test commands after migration

```bash
cd backend
pytest -q
```

```bash
cd backend
ruff check app
```

```bash
mkdocs build --strict
```

## 6) Packaging and release

```bash
cd backend
python -m build
python -m twine check dist/*
```

Publish to TestPyPI/PyPI via CI trusted publishing.
