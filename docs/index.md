# FluxRules

FluxRules is a Python rule evaluation toolkit with multiple engine implementations and optional FastAPI endpoints.

Use FluxRules when you want to keep decision logic outside application control flow and evaluate it consistently in tests, services, and APIs.

## Core Capabilities

- Evaluate a ruleset against facts with the top-level Python API.
- Run rule evaluation through the PHREAK engine (stateless or streaming mode).
- Validate rulesets before evaluation.
- Retrieve evaluation explanations by execution id.
- Run optional HTTP endpoints for evaluate, validate, explain, and health.

## Advanced Capabilities

- Build stateful and streaming evaluation flows.
- Load rules from YAML and CSV decision tables.
- Register and execute custom action handlers.
- Normalize heterogeneous facts using loader and pipeline stages.
- Model nested facts and cross-fact joins.

See [Usage: Advanced Capabilities](usage/advanced-capabilities.md) for runnable example mapping.

## Project Scope

This repository currently focuses on:

- In-process Python library usage.
- Optional API layer and integrations through extras.
- Developer-facing examples and tests.

This repository does not include a hosted control plane.

The package source is in `src/fluxrules`, and examples are in `examples/`.

## Start Here

- [Getting Started](getting-started.md)
- [Installation](installation.md)
- [Quickstart](quickstart.md)
- [Architecture](architecture.md)
- [Usage Overview](usage/index.md)
- [Advanced Capabilities](usage/advanced-capabilities.md)
