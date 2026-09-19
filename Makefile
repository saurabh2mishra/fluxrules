.PHONY: help check-uv install dev lint format test test-fast test-full test-perf test-sequential test-cov type-check docs docs-serve clean build publish

help:
	@echo "FluxRules Makefile Targets\n"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'
	@echo "\nQuick Start:"
	@echo "  make install   # Install base dependencies"
	@echo "  make dev       # Install all dev dependencies (required for lint, format, type-check)"
	@echo "  make lint      # Check code style"
	@echo "  make format    # Auto-format code"
	@echo "  make test      # Run all tests"

check-uv:
	@python scripts/check_uv.py

install: check-uv
	uv sync

dev: check-uv
	uv sync --extra dev --extra docs
	uv run pre-commit install

lint: check-uv
	uv run ruff check src/ tests/

format: check-uv
	uv run ruff format src/ tests/
	uv run ruff check --fix src/ tests/

test: check-uv
	uv run pytest tests/ -v -m "not performance"

test-fast: check-uv
	uv run pytest tests/unit tests/integration -n auto -q

test-full: check-uv
	uv run pytest tests/ -n auto -q -m "not performance"

test-perf: check-uv
	uv run pytest tests/ -m performance -p no:xdist -v

test-sequential: check-uv
	uv run pytest tests/ -v --tb=short

test-cov: check-uv
	uv run pytest tests/ -v --cov=src/fluxrules --cov-report=term-missing

type-check: check-uv
	uv run mypy src/fluxrules --ignore-missing-imports

docs: check-uv
	uv run mkdocs build

docs-serve: check-uv
	uv run mkdocs serve

clean:
	rm -rf dist/ build/ *.egg-info .pytest_cache .mypy_cache .ruff_cache htmlcov/
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true

build: check-uv
	uv build

publish: build
	uv run --with twine twine upload dist/*
