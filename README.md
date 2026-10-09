[![MIT License](https://img.shields.io/badge/license-MIT-brightgreen.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/)
[![CI](https://github.com/saurabh2mishra/fluxrules/actions/workflows/ci.yml/badge.svg)](https://github.com/saurabh2mishra/fluxrules/actions/workflows/ci.yml)
[![codecov](https://codecov.io/gh/fluxrules/fluxrules/branch/main/graph/badge.svg)](https://codecov.io/gh/fluxrules/fluxrules)

# FluxRules

FluxRules is a Python library for authoring rules and evaluating them against facts. It is loosely based on the concepts from Drools’ Phreak engine.

Use FluxRules to keep decision logic separate from application flow and evaluate rules consistently across facts.

## Core Capabilities

- Evaluate a ruleset against facts using the top-level Python API.
- Run rule evaluation through FluxRules’ Phreak engine in stateless or streaming mode.
- Validate rulesets before evaluation.
- Retrieve evaluation explanations
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

For more details see the [installation guide](docs/installation.md).

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

## Using the engine directly

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
see [API](/docs/api.md) for more detail.

## CLI (Optional)

```bash
uv sync --extra cli
fluxrules --help
```

## Documentation

[Documentation](https://saurabh2mishra.github.io/fluxrules/)

## Contributing

[CONTRIBUTING](CONTRIBUTING.md) & [CODE OF CONDUCT](CODE_OF_CONDUCT.md)

## Security

[SECURITY](SECURITY.md)

## License

[LICENSE](LICENSE)