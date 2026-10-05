[![MIT License](https://img.shields.io/badge/license-MIT-brightgreen.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/)
[![CI](https://github.com/saurabh2mishra/fluxrules/actions/workflows/ci.yml/badge.svg)](https://github.com/saurabh2mishra/fluxrules/actions/workflows/ci.yml)
[![codecov](https://codecov.io/gh/fluxrules/fluxrules/branch/main/graph/badge.svg)](https://codecov.io/gh/fluxrules/fluxrules)

# FluxRules

FluxRules is a Python library for authoring rules and evaluating them against facts. It is loosely based on the concepts from Drools’ Phreak engine and provides optional FastAPI endpoints.

Use FluxRules to keep decision logic separate from application control flow and evaluate rules consistently across tests, services, and APIs.

## Core Capabilities

- Evaluate a ruleset against facts using the top-level Python API.
- Run rule evaluation through FluxRules’ Phreak engine in stateless or streaming mode.
- Validate rulesets before evaluation.
- Retrieve evaluation explanations by execution ID.
- Use optional HTTP endpoints for evaluation, validation, explanations, and health checks.

## Requirements

- Python 3.10+

## Installation

For local development, clone the repository and install the project with uv:

```bash
git clone https://github.com/fluxrules/fluxrules.git
cd fluxrules
uv sync --extra dev
```

This creates the project environment and installs FluxRules with its development
tools. To install the published package in a virtual environment managed by uv:

```bash
uv venv
uv pip install fluxrules
```

Install an optional extra in the checkout with `uv sync`, for example:

```bash
uv sync --extra api
uv sync --extra sql
uv sync --extra redis
uv sync --extra otel
uv sync --extra yaml
uv sync --extra cli
uv sync --extra docs
uv sync --extra all
```

For a published package, use `uv pip install 'fluxrules[api]'` (replace `api`
with the extra you need). Pip is also supported; see the
[installation guide](docs/installation.md) for its virtual-environment commands.
The `all` extra combines the API, SQL, Redis, OpenTelemetry, YAML, CLI, and
documentation integrations. The core install includes the dependencies needed
for `import fluxrules`, the canonical `Rule`, and the top-level evaluation API.

## Quick Use

---

## Your First Rule

```python
from fluxrules.domain import Rule
from fluxrules.engine.phreak import PhreakEngine

# Create a rule
rule = Rule(
    name="high_value_transaction",
    domain="test",
    condition_dsl={
        "type": "condition",
        "field": "amount",
        "op": ">",
        "value": 5000,
    },
    action="manual_review",
    priority=100,
)

# Create an engine and load the rule
engine = PhreakEngine()
engine.load_rules([rule])

# Evaluate a fact
fact = {"amount": 6000}
result = engine.evaluate(fact)

print(f"Matched rules: {result.fired_rules}")
print(f"Actions: {result.actions}")
```

**Output:**
```
Matched rules: [1]
Actions: ['manual_review']
```

## API Server (Optional)

```bash
uv sync --extra api
uvicorn fluxrules.api.app:create_app --factory --reload
```

Core always-on routes include:

- `GET /health`
- `GET /v1/health`
- `POST /evaluate`
- `POST /validate`
- `GET /v1/executions/{execution_id}`
- `POST /v1/rulesets/{ruleset_id}/simulate`

Additional routers are loaded when optional dependencies are available.

## CLI (Optional)

```bash
uv sync --extra cli
fluxrules --help
```

## Development

This repository uses the root `.venv` environment. If `VIRTUAL_ENV` points to
another environment, clear it before running `uv` commands so uv selects the
project environment:

```bash
unset VIRTUAL_ENV
```

```bash
python scripts/check_uv.py
uv sync --extra dev
uv run pytest tests/ -v
```

FluxRules requires **uv 0.8.0 or newer** because the committed lockfile uses
uv's revision-2 format. If the check reports an older or missing uv, install it
through the project package index:

```bash
python -m pip install \
    --index-url https://p-nexus-3.development.nl.eu.abnamro.com:8443/repository/python-group/simple/ \
    'uv>=0.8'
```

The index URL is used only for the uv installation command; it is deliberately
not part of `pyproject.toml`, `uv.lock`, or project dependency resolution.

Common commands:

- `make lint`
- `make type-check`
- `make test`
- `make docs`
- `make build` (build the sdist and wheel with the locked developer toolchain)

## Documentation

- Docs index: [docs/index.md](docs/index.md)
- MkDocs config: [mkdocs.yml](mkdocs.yml)

Local docs preview:

```bash
uv sync --extra dev
uv run mkdocs serve
```

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) and [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md).

## Security

See [SECURITY.md](SECURITY.md).

## License

MIT. See [LICENSE](LICENSE).