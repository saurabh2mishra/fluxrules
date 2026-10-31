# Development

Setup, testing, and contributing to FluxRules.

## Quick Start

- **[Contributing](../contributing.md)**: Contribution guidelines
- **[Testing](testing.md)**: Running tests locally
- **[Backlog](backlog.md)**: Designed but not yet shipped work

## Setup

FluxRules uses [uv](https://docs.astral.sh/uv/) for dependency management. As a
published library, it does **not** commit `uv.lock` (it is gitignored), so a
clean sync resolves the latest versions allowed by the ranges declared in
`pyproject.toml`.

### Prerequisites

- **uv** ≥ 0.7 (`curl -LsSf https://astral.sh/uv/install.sh | sh`)
- **Python** ≥ 3.11 (uv will download a matching interpreter if none is present)

### Dev environment

The project environment is the repository-root `.venv`. If your shell has
`VIRTUAL_ENV` set to another project environment, clear it before running uv:

```bash
unset VIRTUAL_ENV
```

```bash
git clone https://github.com/saurabh2mishra/fluxrules.git
cd fluxrules

# Recommended: creates .venv, installs the dev + docs extras
# (including pytest-xdist for `pytest -n auto`), and wires up pre-commit hooks.
make dev

# Equivalent explicit command (dev group is installed by default):
uv sync --group docs
```

`uv.lock` is committed, so every contributor and CI resolve the same versions.
Pass `--locked` to fail fast when `pyproject.toml` and the lock have drifted:

```bash
uv sync --group docs --locked      # use uv.lock exactly; error if it is stale
```

### Private index / offline mirrors

By default uv resolves packages from PyPI. Behind a corporate mirror, point uv
(and pip fallbacks) at your index before syncing:

```bash
export UV_INDEX_URL="https://your-mirror/simple/"
export PIP_INDEX_URL="https://your-mirror/simple/"
uv sync --group docs
```

Use `--offline` to resolve entirely from uv's local cache when the network is
unavailable.

### Library-only install

To use FluxRules as a dependency (no dev tooling):

```bash
pip install fluxrules            # from PyPI
pip install -e . --group dev     # editable, with dev tooling (pip >= 25.1)
```


## Development Workflow

1. Create feature branch
2. Write tests for new behavior
3. Implement feature
4. Run full test suite
5. Update documentation
6. Submit pull request

See [Contributing](../contributing.md) for more details.
