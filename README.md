[![MIT License](https://img.shields.io/badge/license-MIT-brightgreen.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/)
[![CI](https://github.com/saurabh2mishra/fluxrules/actions/workflows/ci.yml/badge.svg)](https://github.com/saurabh2mishra/fluxrules/actions/workflows/ci.yml)
[![codecov](https://codecov.io/gh/saurabh2mishra/fluxrules/branch/main/graph/badge.svg)](https://codecov.io/gh/saurabh2mishra/fluxrules)

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
from fluxrules import F, Rule, evaluate

rule = Rule(
    name="high_value_transaction",
    conditions=F("amount") > 5000,
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
from fluxrules import F, PhreakEngine, Rule

rule = Rule(
    name="high_value_transaction",
    domain="payments",
    conditions=F("amount") > 5000,
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

## How it works

You call `evaluate(facts)` with a dictionary of field values. fluxrules returns which rules matched and what actions they produced. That's the whole contract.

### What happens inside each call

```
facts (dict)
  |
  +-- Field check: rules that need a field not present in facts are skipped
  |
  +-- Value check: rules whose conditions provably cannot match are skipped
  |
  +-- Condition evaluation: only the surviving rules are tested
  |
  +-- EvaluationResult: fired rule ids, actions, optional explanation
```

Within a single call, identical sub-expressions are evaluated once and reused across all rules. On shared workloads this eliminates roughly 96% of redundant leaf evaluations.

### Design choices

fluxrules is built around one idea: **evaluate(facts) is a pure function**. Every call is independent. There is no shared state between calls, no side-effects, and no memory of previous evaluations. This makes it safe to run across threads, processes, or load-balanced instances without coordination.

That choice drives everything else:

- Rules are evaluated against one fact dictionary at a time. Cross-fact rules (joining two entity types) use a separate `CrossFactEngine`.
- There is no truth maintenance. fluxrules does not track which rules fired previously or retract consequences when facts change.
- Streaming mode (`streaming_mode=True`) is the one exception: it caches condition results across calls for long-lived engine instances. Use it when you own the engine lifecycle (a single-process event loop). Use stateless mode everywhere else.

### Lazy evaluation

fluxrules skips work at every level it can:

- Rules whose required fields are missing from the incoming fact are skipped before any condition is evaluated.
- In streaming mode, rule segments whose fields have not changed since the last call are not re-evaluated.
- AND conditions stop as soon as the first failing sub-condition is found. OR conditions stop as soon as the first passing one is found.
- If the incoming facts are identical to the previous call (streaming mode), the entire evaluation is skipped and an empty result is returned immediately.

## Documentation

[DOCS](https://saurabh2mishra.github.io/fluxrules/)

## Contributing

[CONTRIBUTING](CONTRIBUTING.md) & [CODE OF CONDUCT](CODE_OF_CONDUCT.md)

## Security

[SECURITY](SECURITY.md)

## License

[LICENSE](LICENSE)