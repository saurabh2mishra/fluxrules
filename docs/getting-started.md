# Getting Started

This page helps you run FluxRules locally in a few minutes.

## Prerequisites

- Python 3.10 or newer
- uv (recommended) or pip

## Install with uv

The recommended setup is to use uv for dependency management and a local virtual environment:

```bash
git clone https://github.com/fluxrules/fluxrules.git
cd fluxrules
uv sync --extra dev
```

This creates the project environment and installs the package plus the developer tooling.

## Install with pip

If you prefer pip, the project also installs normally with a standard virtual environment:

```bash
git clone https://github.com/fluxrules/fluxrules.git
cd fluxrules
python -m venv .venv
source .venv/bin/activate
pip install .
```

For API endpoints, install extras:

```bash
pip install '.[api]'
# or with uv
uv pip install '.[api]'
```

## Minimal Evaluation Flow

1. Define a ruleset.
2. Evaluate facts.
3. Inspect matched rules and trace.

See [Quickstart](quickstart.md) for a full example.

## Local Docs

```bash
uv sync --extra dev
uv run mkdocs serve
```

Open the local URL shown by MkDocs.

## Run the project tests

```bash
uv run pytest tests/ -v
```

This is the preferred way to validate the project in a local environment.
