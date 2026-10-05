[![MIT License](https://img.shields.io/badge/license-MIT-brightgreen.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/)
[![CI](https://github.com/fluxrules/fluxrules/actions/workflows/ci.yml/badge.svg)](https://github.com/fluxrules/fluxrules/actions/workflows/ci.yml)
[![codecov](https://codecov.io/gh/fluxrules/fluxrules/branch/main/graph/badge.svg)](https://codecov.io/gh/fluxrules/fluxrules)

# FluxRules

FluxRules is a Business Rule Evaluation library with optional API and integration layers.

## Repository Scope

This repository contains:

- A Python package under `src/fluxrules`
- Rule evaluation powered by the PHREAK engine (stateless and streaming modes)
- Optional FastAPI routes under `src/fluxrules/api/routes`
- Optional integrations enabled through extras in `pyproject.toml`
- Documentation under `docs/`
- Runnable examples under `examples/`
- Automated tests under `tests/`

This repository does not include a hosted control plane.

## Requirements

- Python 3.10+

## Installation

Install the published wheel when available, or install from a checkout while
developing the project:

```bash
pip install fluxrules
```

For a checkout:

```bash
git clone https://github.com/fluxrules/fluxrules.git
cd fluxrules
pip install .
```

Optional extras from `pyproject.toml`:

```bash
pip install '.[api]'
pip install '.[sql]'
pip install '.[redis]'
pip install '.[otel]'
pip install '.[yaml]'
pip install '.[cli]'
pip install '.[docs]'
pip install '.[all]'
```

The `all` extra combines the API, SQL, Redis, OpenTelemetry, YAML, CLI, and
documentation integrations. The core install includes the dependencies needed
for `import fluxrules`, the canonical `Rule`, and the top-level evaluation API.

## Quick Use

```python
from fluxrules import Rule, evaluate, explain
from fluxrules.domain.models import Ruleset

rule = Rule(
    name="adult",
    condition_dsl={"type": "condition", "field": "age", "op": ">=", "value": 18},
    action="allow",
)

ruleset = Ruleset(group="eligibility", rules=(rule.to_engine_rule(),))
result = evaluate(ruleset, {"age": 30})

print(result.matched_rule_ids)
print(explain(result.execution_id))
```

## API Server (Optional)

```bash
pip install '.[api]'
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
pip install '.[cli]'
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