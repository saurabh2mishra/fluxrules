# FluxRules

FluxRules is a Python toolkit for authoring rules and evaluating them against facts. It is loosely based on the concepts from Drools’ Phreak engine and provides optional FastAPI endpoints.

Use FluxRules to keep decision logic separate from application control flow and evaluate rules consistently across tests, services, and APIs.

## Core Capabilities

- Evaluate a ruleset against facts using the top-level Python API.
- Run rule evaluation through FluxRules’ Phreak engine in stateless or streaming mode.
- Validate rulesets before evaluation.
- Retrieve evaluation explanations by execution ID.
- Use optional HTTP endpoints for evaluation, validation, explanations, and health checks.

## Advanced Capabilities

- Build stateful and streaming evaluation flows.
- Load simple or nested rules directly from YAML files.
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
