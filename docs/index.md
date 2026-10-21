# FluxRules

FluxRules is a lightweight Python library for defining and managing business rules. It evaluates rules against facts using a fast, deterministic engine inspired by Drools’ Phreak algorithm.

## Core Capabilities

- Create Rules 
- Validate the rules
- Evaluate a ruleset against facts using the top-level Python API.
- Run rule evaluation through FluxRules’ Phreak engine in stateless or streaming mode.
- Retrieve evaluation explanations.
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
