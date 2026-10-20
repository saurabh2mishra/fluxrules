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
from fluxrules import Rule, evaluate

rule = Rule(
    name="high_value_transaction",
    conditions={"type": "condition", "field": "amount", "op": ">", "value": 5000},
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
    conditions={"type": "condition", "field": "amount", "op": ">", "value": 5000},
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

### Evaluation pipeline

Each call to `evaluate()` runs a fact dictionary through four stages:

```
facts (dict)
  │
  ├─ Alpha prefilter — rules whose required fields are absent are skipped
  │
  ├─ BitMaskLinker — bitmask check confirms all required segment fields are present
  │
  ├─ Per-rule condition evaluation — only linked rules are tested
  │
  └─ EvaluationResult — fired rule ids, actions, and optional explanation
```

A per-cycle leaf memo collapses repeated sub-expression evaluations within a
single call (~96% reduction on shared leaves in typical rulesets).

### What is borrowed from Drools Phreak

- **BitMaskLinker** — rules are "linked" only when the incoming fact contains all
  fields their conditions reference; unlinked rules are skipped entirely before
  any condition is tested.
- **SegmentNetwork** — rules are grouped by their condition field-set; only the
  segments whose fields appear in the changed fact are re-evaluated.
- **Dirty-segment tracking** (`LazyEvaluationMixin`) — in streaming mode,
  segments whose inputs have not changed since the last call are not re-evaluated.
- **Salience-ordered Agenda** — a `heapq`-backed agenda orders fired rules by
  priority; populated in streaming mode for ordered action dispatch.

### What is intentionally left out

- **No beta network / join nodes.** fluxrules evaluates one fact at a time.
  `enforce_single_fact_boundary` raises at load time if a rule references more
  than one fact type. Cross-fact rules use a separate `CrossFactEngine`.
- **No truth maintenance system (TMS).** There is no consequence retraction;
  each call is independent and produces no side-effects on engine state.
- **No tuple-based partial match memory.** Without multi-fact joins, there is
  nothing to accumulate between rule firings.

These omissions are deliberate. fluxrules is a **stateless scoring function**:
`evaluate(facts) → EvaluationResult`. It is designed for concurrent HTTP
deployments where each request is independent and shared mutable state between
calls is a liability, not a feature.

### Stateless vs. streaming mode

In the default stateless mode, every `evaluate()` call starts from a clean
engine state. This is safe to use across threads and processes with no
coordination.

`streaming_mode=True` adds cross-call caching for long-lived engine instances:
dirty-segment tracking and the salience agenda are preserved between calls so
that unchanged segments are not re-evaluated. Use streaming mode when you control
the engine lifecycle (e.g., a single-process event stream), and stateless mode
everywhere else.

## Documentation

[DOCS](https://saurabh2mishra.github.io/fluxrules/)

## Contributing

[CONTRIBUTING](CONTRIBUTING.md) & [CODE OF CONDUCT](CODE_OF_CONDUCT.md)

## Security

[SECURITY](SECURITY.md)

## License

[LICENSE](LICENSE)