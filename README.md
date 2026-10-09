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

## Your First Rule

```python
from fluxrules import Rule, evaluate

rule = Rule(
    name="high_value_transaction",
    condition_dsl={"type": "condition", "field": "amount", "op": ">", "value": 5000},
    action="manual_review",
)

result = evaluate(rule, {"amount": 6000})

print(f"Fired rules: {result.fired_rules}")
print(f"Actions: {result.actions}")
```

**Output:**
```
Fired rules: [1]
Actions: ['manual_review']
```

Constructing a `Rule` does no I/O and `evaluate()` takes rules directly, so
there is nothing to configure to get an answer. `evaluate()` also accepts a list
of rules, or a named `Ruleset`.

Every evaluation path returns the same `EvaluationResult`, whose `fired_rules`
is the list of rules that matched.

## Using the engine directly

Load rules once and evaluate many facts against them. This is the path to reach
for in a service, and it exposes the engine's diagnostics.

```python
from fluxrules import PhreakEngine, Rule

rule = Rule(
    name="high_value_transaction",
    domain="payments",
    condition_dsl={"type": "condition", "field": "amount", "op": ">", "value": 5000},
    action="manual_review",
    priority=100,
)

engine = PhreakEngine()
engine.load_rules([rule])

for fact in ({"amount": 6000}, {"amount": 10}):
    result = engine.evaluate(fact)
    print(fact, "->", result.fired_rules, result.actions)
```

To persist a rule, call `rule.save()`, or pass `persist=True` when constructing
it. See the [persistence guide](docs/persistence.md).

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

See [LICENSE](LICENSE).