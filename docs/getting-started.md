# Getting Started

This page gets you from nothing to a working rule in a few minutes.

## Prerequisites

- Python 3.11 or newer
- uv (recommended) or pip

## Install with uv

Add FluxRules to your project from PyPI:

```bash
uv add fluxrules
```

Or, to try it in a fresh virtual environment without a project:

```bash
uv venv
uv pip install fluxrules
```

## Install with pip

Create a virtual environment and install the release from PyPI:

```bash
python -m venv .venv
source .venv/bin/activate
pip install fluxrules
```

## Optional extras

The base package is enough to write and evaluate rules. Add an extra for the
feature you need, for example the HTTP API:

```bash
pip install 'fluxrules[api]'
# or with uv
uv add 'fluxrules[api]'
```

See [Installation](installation.md) for the full list of extras.

## Check that it works

```python
from fluxrules import F, Rule, evaluate

rule = Rule(name="adult", conditions=F("age") >= 18, action="allow")

result = evaluate(rule, {"age": 30})
print(result.fired_rules)  # the id of the rule that matched
print(result.actions)      # ['allow']
```

## Minimal Evaluation Flow

1. Define a ruleset.
2. Evaluate facts.
3. Inspect matched rules and trace.

See [Quickstart](quickstart.md) for a full example, and
[Authoring Rules](authoring-rules.md) for the ways to write a condition.

## Working on FluxRules itself

See [Contributing](contributing.md) for the
full contributor guide.
