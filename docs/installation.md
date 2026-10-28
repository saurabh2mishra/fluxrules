# Installation

## Requirements

- **Python 3.11 or newer.** FluxRules 1.x is tested on Python 3.11 and 3.12.
- Python 3.10 and older are not supported. On those versions pip will not install
  FluxRules 1.x and reports that no matching distribution was found. Upgrade
  Python, or pin `fluxrules<1.0` to stay on the last release that supported 3.10.

Check your version before installing:

```bash
python --version  # must print 3.11 or higher
```

## Install from PyPI

The simplest way to add FluxRules to your project:

```bash
pip install fluxrules
```

With [uv](https://docs.astral.sh/uv/) (recommended for new projects):

```bash
uv add fluxrules
```

That is all you need to start. No git clone required.

## Optional extras

The base package includes the core rule engine. Install extras to unlock integrations:

| Extra | What it adds |
|---|---|
| `api` | FastAPI HTTP server, SQLAlchemy ORM, JWT auth |
| `sql` | SQLAlchemy + Alembic for database persistence |
| `redis` | Redis-backed persistence adapter |
| `otel` | OpenTelemetry tracing |
| `yaml` | YAML rule file loading |
| `cli` | `fluxrules` command-line tool |
| `all` | Everything above |

```bash
pip install 'fluxrules[api]'
pip install 'fluxrules[sql]'
pip install 'fluxrules[yaml]'
pip install 'fluxrules[cli]'
pip install 'fluxrules[all]'
```

With uv:

```bash
uv add 'fluxrules[api]'
uv add 'fluxrules[sql]'
uv add 'fluxrules[all]'
```

## Verify the install

```bash
python -c "import fluxrules; print(fluxrules.__version__)"
```


