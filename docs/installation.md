# Installation

This is the reference install guide for FluxRules. For a quick hands-on local setup,
see [getting-started.md](getting-started.md).

## Recommended: install with uv

Use uv for a fast project-local environment and dependency management:

```bash
git clone https://github.com/saurabh2mishra/fluxrules.git
cd fluxrules
uv sync --extra dev
```

This creates the project virtual environment and installs the core package plus the
local development toolchain.

## Install the published package

After creating a virtual environment, install the published package into it:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install fluxrules
```

## Install from a checkout

```bash
git clone https://github.com/saurabh2mishra/fluxrules.git
cd fluxrules
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install .
```

For the same workflow with uv:

```bash
git clone https://github.com/saurabh2mishra/fluxrules.git
cd fluxrules
uv sync
```

The base package requires `pydantic>=2.8` (declared in `pyproject.toml`).

## Optional extras

Install extras into the active environment:

```bash
python -m pip install '.[api]'
python -m pip install '.[sql]'
python -m pip install '.[redis]'
python -m pip install '.[otel]'
python -m pip install '.[yaml]'
python -m pip install '.[cli]'
python -m pip install '.[docs]'
```

With uv, use:

```bash
uv pip install '.[api]'
uv pip install '.[sql]'
uv pip install '.[redis]'
uv pip install '.[otel]'
uv pip install '.[yaml]'
uv pip install '.[cli]'
uv pip install '.[docs]'
```

## Install all extras

```bash
python -m pip install '.[all]'
# or
uv pip install '.[all]'
```

The base package is the supported core API. Extras add integrations without changing
core `Rule`, `Ruleset`, and `PhreakEngine` behavior.

## Development install

```bash
python scripts/check_uv.py
uv sync --extra dev
```

If you want the project build wrapper, `make build` is available, but the direct uv
command is the simplest and most portable option:

```bash
uv build
```

## Verify the install

From an active virtual environment:

```bash
python -c "import fluxrules; print(fluxrules.__version__)"
```

From a project checkout managed by uv:

```bash
uv run python -c "import fluxrules; print(fluxrules.__version__)"
```

## Build and verify a wheel

```bash
uv build
python -m venv /tmp/fluxrules-wheel-smoke
/tmp/fluxrules-wheel-smoke/bin/python -m pip install dist/*.whl
/tmp/fluxrules-wheel-smoke/bin/python -c "import fluxrules; print(fluxrules.__version__)"
```
