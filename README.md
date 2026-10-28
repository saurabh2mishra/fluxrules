[![MIT License](https://img.shields.io/badge/license-MIT-brightgreen.svg)](https://github.com/saurabh2mishra/fluxrules/blob/main/LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/)
[![CI](https://github.com/saurabh2mishra/fluxrules/actions/workflows/ci.yml/badge.svg)](https://github.com/saurabh2mishra/fluxrules/actions/workflows/ci.yml)
[![codecov](https://codecov.io/gh/saurabh2mishra/fluxrules/branch/main/graph/badge.svg)](https://codecov.io/gh/saurabh2mishra/fluxrules)

# FluxRules

FluxRules is a lightweight Python library for defining and managing business rules. It evaluates rules against facts using a fast, deterministic engine inspired by Drools’ Phreak algorithm.

## Core Capabilities

- Evaluate a ruleset against facts using the top-level Python API.
- Run rule evaluation through FluxRules’ Phreak engine in stateless or streaming mode.
- Validate rulesets before evaluation.
- Retrieve evaluation explanations
- Use optional HTTP endpoints for evaluation, validation, explanations, and health checks.

## Requirements

- **Python 3.11 or newer.** FluxRules 1.x is tested on Python 3.11, 3.12, 3.13 and 3.14.
- Python 3.10 and older are not supported. On those versions pip will not install
  FluxRules 1.x and reports that no matching distribution was found. Upgrade
  Python, or pin `fluxrules<1.0` to stay on the last release that supported 3.10.

Check your version before installing:

```bash
python --version  # must print 3.11 or higher
```

## Installation

Install FluxRules from [PyPI](https://pypi.org/project/fluxrules/):

```bash
pip install fluxrules
```

Or, if you use [uv](https://docs.astral.sh/uv/):

```bash
uv add fluxrules
```

The base package is all you need to write and evaluate rules. Add an extra only for the feature you want:

```bash
pip install 'fluxrules[api]'     # HTTP endpoints
pip install 'fluxrules[sql]'     # database persistence
pip install 'fluxrules[redis]'   # Redis persistence
pip install 'fluxrules[otel]'    # OpenTelemetry tracing
pip install 'fluxrules[yaml]'    # load rules from YAML
pip install 'fluxrules[cli]'     # command-line tool
pip install 'fluxrules[all]'     # everything above
```

For more details see the [installation guide](https://saurabh2mishra.github.io/fluxrules/installation/).

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

You do not need a database, a server, or any setup to get a result: creating a
`Rule` touches nothing external, and `evaluate()` runs the rules you pass it
right away. You can pass a single rule, a list of rules, or a
[Ruleset](https://github.com/saurabh2mishra/fluxrules/blob/main/src/fluxrules/domain/models.py#L171-L182) (a named group of rules).

How to write rule(s)? [Authoring Rules](https://saurabh2mishra.github.io/fluxrules/authoring-rules/) 

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
it. See the [persistence guide](https://saurabh2mishra.github.io/fluxrules/persistence/).

## API Server (Optional)

```bash
uv sync --extra api
uvicorn fluxrules.api.app:create_app --factory --reload
```
see [API](https://saurabh2mishra.github.io/fluxrules/api/) for more detail.

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

By default, FluxRules is **stateless**. Each `evaluate(facts)` call stands on its own: it reads the facts you pass in, returns what matched, and keeps nothing afterwards. Because calls share no state, you can run them in parallel across threads, processes, or servers with no coordination.

Two features keep state on purpose, and you opt into each:

- **Streaming mode** (`streaming_mode=True`): a long-lived engine remembers results between calls and skips work that has not changed, so repeated evaluations on the same engine run faster. Use it when you own that engine (for example, a single-process event loop). Use the stateless default everywhere else.
- **Cross-fact joins** (`CrossFactEngine`): to match a rule across more than one fact (say, an order and its customer), the engine holds those facts in memory so it can line them up.

FluxRules does no truth maintenance: when facts change, it does not undo rules that fired earlier. Each run just reports what matches right now.

### Lazy evaluation

fluxrules skips work at every level it can:

- Rules whose required fields are missing from the incoming fact are skipped before any condition is evaluated.
- In streaming mode, rule segments whose fields have not changed since the last call are not re-evaluated.
- AND conditions stop as soon as the first failing sub-condition is found. OR conditions stop as soon as the first passing one is found.
- If the incoming facts are identical to the previous call (streaming mode), the entire evaluation is skipped and an empty result is returned immediately.

## Documentation

[Docs](https://saurabh2mishra.github.io/fluxrules/)

## Architecture 

[Architecture](https://saurabh2mishra.github.io/fluxrules/architecture/)

## Contributing

[Contributing](https://github.com/saurabh2mishra/fluxrules/blob/main/CONTRIBUTING.md) & [Code of Conduct](https://github.com/saurabh2mishra/fluxrules/blob/main/CODE_OF_CONDUCT.md)

## Security

[Security](https://github.com/saurabh2mishra/fluxrules/blob/main/SECURITY.md)

## License

[License](https://github.com/saurabh2mishra/fluxrules/blob/main/LICENSE)