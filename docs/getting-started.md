# Getting Started

This page helps you run FluxRules locally in a few minutes.

## Prerequisites

- Python 3.10 or newer
- pip or uv

## Install

```bash
git clone https://github.com/fluxrules/fluxrules.git
cd fluxrules
pip install .
```

For API endpoints, install extras:

```bash
pip install '.[api]'
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
