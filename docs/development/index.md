# Development

Setup, testing, and contributing to FluxRules.

## Quick Start

- **[Contributing](../contributing.md)** - Contribution guidelines
- **[Testing](testing.md)** - Running tests locally

## Setup

FluxRules uses [uv](https://docs.astral.sh/uv/) for dependency management. As a
published library, it does **not** commit `uv.lock` (it is gitignored), so a
clean sync resolves the latest versions allowed by the ranges declared in
`pyproject.toml`.

### Prerequisites

- **uv** ≥ 0.7 (`curl -LsSf https://astral.sh/uv/install.sh | sh`)
- **Python** ≥ 3.10 (uv will download a matching interpreter if none is present)

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

# Equivalent explicit command:
uv sync --extra dev --extra docs
```

The first `uv sync` writes a local `uv.lock`. Because that file is gitignored,
it stays on your machine and is not shared; a teammate's clean sync may resolve
slightly newer patch versions within the same ranges. If you want a byte-pinned,
strictly reproducible environment, generate and keep your own lock, then pass
`--locked` on subsequent syncs so uv fails fast when `pyproject.toml` drifts:

```bash
uv lock                                        # create uv.lock locally
uv sync --extra dev --extra docs --locked      # reuse it exactly
```

### Private index / offline mirrors

By default uv resolves packages from PyPI. Behind a corporate mirror, point uv
(and pip fallbacks) at your index before syncing:

```bash
export UV_INDEX_URL="https://your-mirror/simple/"
export PIP_INDEX_URL="https://your-mirror/simple/"
uv sync --extra dev --extra docs
```

Use `--offline` to resolve entirely from uv's local cache when the network is
unavailable.

### Library-only install

To use FluxRules as a dependency (no dev tooling):

```bash
pip install fluxrules            # from PyPI
pip install -e ".[dev]"          # editable, with dev extras
```


## Development Workflow

1. Create feature branch
2. Write tests for new behavior
3. Implement feature
4. Run full test suite
5. Update documentation
6. Submit pull request

See [Contributing](../contributing.md) for more details.
