# Installation

## Install the Package

```bash
pip install fluxrules
```

For a checkout or local development:

```bash
git clone https://github.com/fluxrules/fluxrules.git
cd fluxrules
pip install .
```

The base package requires `pydantic>=2.8` (declared in `pyproject.toml`).

## Optional Extras

```bash
pip install '.[api]'
pip install '.[sql]'
pip install '.[redis]'
pip install '.[otel]'
pip install '.[yaml]'
pip install '.[cli]'
pip install '.[docs]'
```

## Install All Extras

```bash
pip install '.[all]'
```

The base package is the supported core API. Extras add integrations without
changing the core `Rule`, `Ruleset`, and `PhreakEngine` contract.

## Development Install

```bash
python scripts/check_uv.py
uv sync --extra dev
```

`make build` uses uv's native build command, matching the CI wheel smoke job
without adding a separate build package to the locked runtime/development
dependency graph.

## Build and Verify a Wheel

```bash
make build
python -m venv /tmp/fluxrules-wheel-smoke
/tmp/fluxrules-wheel-smoke/bin/python -m pip install dist/*.whl
/tmp/fluxrules-wheel-smoke/bin/python -c "import fluxrules; print(fluxrules.__version__)"
```

## Verify

```bash
python -c "import fluxrules; print(fluxrules.__version__)"
```
