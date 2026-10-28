# Installation

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

## Requirements

- Python 3.11 or later

