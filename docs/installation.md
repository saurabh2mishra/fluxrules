# Installation

## Requirements

- **Python 3.11 or newer.** FluxRules 1.x is tested on Python 3.11, 3.12, 3.13
  and 3.14.
- Python 3.10 and older are not supported. On those versions pip will not
  install FluxRules 1.x and reports that no matching distribution was found.
  Upgrade Python, or pin `fluxrules<1.0` to stay on the last release that
  supported 3.10.

Check your version before installing:

```bash
python --version  # must print 3.11 or higher
```

## Install with uv

[uv](https://docs.astral.sh/uv/) is the recommended tool. Add FluxRules to your
project from PyPI:

```bash
uv add fluxrules
```

To try it in a fresh virtual environment without a project:

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

That is all you need to start. You do not need to clone the repository.

## Optional extras

The base package is enough to write and evaluate rules. Each extra adds one
integration:

| Extra | What it adds |
|---|---|
| `api` | FastAPI HTTP server, SQLAlchemy ORM, JWT login |
| `sql` | SQLAlchemy and Alembic for database storage |
| `redis` | Redis-backed storage adapter |
| `otel` | OpenTelemetry tracing |
| `yaml` | Loading rules from YAML files |
| `cli` | The `fluxrules` command-line tool |
| `all` | Everything above |

Install one or more extras by name:

```bash
pip install 'fluxrules[api]'
pip install 'fluxrules[yaml,cli]'
pip install 'fluxrules[all]'
```

With uv:

```bash
uv add 'fluxrules[api]'
uv add 'fluxrules[all]'
```

## Verify the install

```bash
python -c "import fluxrules; print(fluxrules.__version__)"
```

Then follow the [Quickstart](quickstart.md) to write your first rule.

To work on FluxRules itself, see [Contributing](contributing.md).
