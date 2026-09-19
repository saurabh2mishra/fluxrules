# Testing

Guidelines for running and writing tests.

## Run Tests

```bash
# All tests
pytest tests/ -v

# With coverage
pytest --cov=app --cov-report=term-missing tests/

# Specific test file
pytest tests/test_engine.py -v

# Parallel (faster)
pytest tests/ -n auto
```

## Test Structure

```
tests/
├── test_engine.py          — Engine tests
├── test_conditions.py      — DSL and condition tests
├── test_integration.py     — End-to-end scenarios
└── performance/            — Benchmarks
```

## Test Standards

- Write tests for new features
- Update tests for behavior changes
- Aim for >80% code coverage
- Use fixtures for common setups

## Linting

```bash
ruff check src/ tests/
```
