"""FluxRules CLI - ``fluxrules`` command-line interface."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import typer
from rich.console import Console
from rich.table import Table

app = typer.Typer(name="fluxrules", help="FluxRules - Business Rule Engine CLI")
console = Console()
err_console = Console(stderr=True)

_SCHEMA_HELP = (
    "Fact schema to check rule fields against: 'package.module:Class' or "
    "'path/to/models.py:Class'. Overrides a fact_schema in the rule file or config."
)
_CONFIG_HELP = (
    "Config file whose fact_schema key applies when neither --schema nor the rule "
    "file names one. Default: $FLUXRULES_CONFIG_FILE, else the first of "
    "fluxrules.yaml, fluxrules.yml, fluxrules.json (here or under config/), "
    "~/.fluxrules.yaml and /etc/fluxrules/config.yaml."
)
_TRUST_HELP = (
    "Allow importing a fact_schema named inside a rule file or a config file found "
    "automatically. Importing runs that module's code, so pass this only for files "
    "you trust. Schemas from --schema or --config are always allowed."
)


@dataclass(frozen=True)
class _Schema:
    """A resolved fact schema and where it was named."""

    model: type
    spec: str
    source: str


def _fail(message: str, code: int = 2) -> typer.Exit:
    """Print *message* to stderr and return the Exit to raise."""
    err_console.print(message, style="red", markup=False, highlight=False, soft_wrap=True)
    return typer.Exit(code=code)


def _read_rules(path: str) -> tuple[Any, list]:
    """Read a JSON or YAML rule file: the parsed file and its canonical Rules."""
    from fluxrules.adapters.loaders.rule_file import read_rule_file
    from fluxrules.domain import Rule

    try:
        document = read_rule_file(path)
        return document, [Rule(**{**item, "persist": False}) for item in document.rules]
    except (OSError, ImportError, ValueError, TypeError) as exc:
        raise _fail(f"Cannot load rules from {path}: {exc}") from None


def _load_rules(path: str) -> list:
    """Load rules from a JSON or YAML file into canonical Rule objects.

    The file holds a single rule mapping, a list of rule mappings, or a mapping
    with a ``rules`` list and an optional ``fact_schema`` (see
    :mod:`fluxrules.adapters.loaders.rule_file`).
    """
    return _read_rules(path)[1]


@dataclass(frozen=True)
class _Named:
    """A fact_schema import string and where it was named."""

    spec: str
    base: Path
    source: str
    trusted: bool  # named by the person running the command


def _config_schema(config: str | None) -> _Named | None:
    """The config file's ``fact_schema``, or ``None``.

    A file named with --config must be readable. A file found automatically
    is optional: if it cannot be read (for example PyYAML is not installed),
    a note is printed and it is treated as having no fact_schema.
    """
    from fluxrules.config.deployment import find_config_file, read_config_file

    explicit = config is not None
    if config is not None:
        if not Path(config).is_file():
            raise _fail(f"Config file not found: {config}")
        path = Path(config)
    else:
        found = find_config_file()
        if found is None:
            return None
        path = found

    def problem(message: str) -> None:
        if explicit:
            raise _fail(message)
        err_console.print(f"Ignoring {path}: {message}", style="dim", markup=False)

    try:
        data = read_config_file(path)
    except Exception as exc:  # unreadable file, bad YAML/JSON, PyYAML missing
        problem(f"cannot read config file {path}: {exc}")
        return None
    spec = data.get("fact_schema")
    if spec is None:
        return None
    if not isinstance(spec, str):
        problem(f"{path}: fact_schema must be an import string such as 'myapp.models:Order'")
        return None
    return _Named(spec=spec, base=path.parent, source=f"config {path}", trusted=explicit)


class _ConfigSchema:
    """The config file's fact_schema, read only when a command first needs it."""

    def __init__(self, config: str | None) -> None:
        self._config = config
        self._read = False
        self._value: _Named | None = None

    def get(self) -> _Named | None:
        if not self._read:
            self._value = _config_schema(self._config)
            self._read = True
        return self._value


def _resolve_schema(
    flag: str | None,
    document: Any,
    config: _ConfigSchema,
    trust: bool,
) -> _Schema | None:
    """Pick the schema: --schema, else the rule file's, else the config's.

    The config file is read only when neither of the first two names one. A
    schema named inside a file the user did not pass explicitly is imported
    only with --trust-schema, because importing runs its code.
    """
    from fluxrules.facts import load_schema

    named: _Named | None
    if flag is not None:
        named = _Named(spec=flag, base=Path.cwd(), source="--schema", trusted=True)
    elif document.fact_schema is not None:
        named = _Named(
            spec=document.fact_schema,
            base=document.path.parent,
            source=f"rule file {document.path}",
            trusted=False,
        )
    else:
        named = config.get()
    if named is None:
        return None
    if not (named.trusted or trust):
        raise _fail(
            f"{named.source} names fact_schema {named.spec!r}. Loading it imports and "
            "runs that module's code. Pass --trust-schema if you trust this file, or "
            "name the schema with --schema."
        )
    try:
        model = load_schema(named.spec, base_dir=named.base)
    except Exception as exc:  # importing user code can raise anything
        raise _fail(
            f"Cannot load fact schema {named.spec!r} (from {named.source}): "
            f"{type(exc).__name__}: {exc}"
        ) from None
    return _Schema(model=model, spec=named.spec, source=named.source)


@app.command()
def evaluate(
    rules: str = typer.Argument(..., help="Path to a rules file (JSON or YAML)"),
    input: str = typer.Argument(..., help="Path to input/event JSON file"),
    format: str = typer.Option("table", help="Output format: table or json"),
    engine: str = typer.Option("PHREAK", help="Engine to use (any registered engine, e.g. PHREAK)"),
    schema: str | None = typer.Option(None, "--schema", help=_SCHEMA_HELP),
    config: str | None = typer.Option(None, "--config", help=_CONFIG_HELP),
    trust_schema: bool = typer.Option(False, "--trust-schema", help=_TRUST_HELP),
    validate_facts: str = typer.Option(
        "off",
        "--validate-facts",
        help="Validate the event against the fact schema first: off, normalize or strict",
    ),
) -> None:
    """Evaluate an event against rules.

    With a fact schema, rules naming a field the schema lacks are refused
    (exit 1), and --validate-facts checks the event too.
    """
    from fluxrules.domain.errors import FactValidationError, FluxRulesError, UnknownFieldError
    from fluxrules.engine import get_available_engines, get_engine
    from fluxrules.facts import VALIDATE_FACTS_MODES

    if engine.upper() not in {name.upper() for name in get_available_engines()}:
        available = ", ".join(get_available_engines())
        console.print(f"[red]Unknown engine '{engine}'. Available: {available}[/red]")
        raise typer.Exit(code=2)
    if validate_facts not in VALIDATE_FACTS_MODES:
        raise _fail(f"--validate-facts must be one of {', '.join(VALIDATE_FACTS_MODES)}")

    document, loaded = _read_rules(rules)
    resolved = _resolve_schema(schema, document, _ConfigSchema(config), trust_schema)
    if validate_facts != "off" and resolved is None:
        raise _fail("--validate-facts needs a fact schema (--schema, or fact_schema in a file)")
    engine_kwargs = (
        {"fact_schema": resolved.model, "validate_facts": validate_facts} if resolved else {}
    )
    try:
        rule_engine = get_engine(engine, **engine_kwargs)
    except (TypeError, ValueError) as exc:
        # e.g. --validate-facts with an attrs schema, or a custom engine that
        # does not take fact_schema.
        raise _fail(f"Cannot build engine {engine!r} with this fact schema: {exc}") from None
    try:
        rule_engine.load_rules(loaded)
    except UnknownFieldError as exc:
        raise _fail(exc.summary, code=1) from None

    with open(input) as f:
        event = json.load(f)

    try:
        result = rule_engine.evaluate(event)
    except FactValidationError as exc:
        # Only raised with validate_facts on, which requires a schema.
        spec = resolved.spec if resolved else ""
        raise _fail(f"Input does not match fact schema {spec}: {exc}", code=1) from None
    except FluxRulesError as exc:
        # e.g. FieldNotFoundError for a nested or misspelled event key.
        raise _fail(str(exc), code=1) from None
    by_id = {rule.id: rule for rule in loaded}
    matched = [by_id[rid] for rid in result.fired_rules if rid in by_id]

    if format == "json":
        console.print_json(
            data={
                "matched_rules": [
                    {
                        "id": rule.id,
                        "name": rule.name,
                        "priority": rule.priority,
                        "action": rule.action,
                    }
                    for rule in matched
                ],
                "actions": result.actions,
            }
        )
    else:
        table = Table(title="Matched Rules")
        table.add_column("ID")
        table.add_column("Name")
        table.add_column("Priority")
        table.add_column("Action")
        for rule in matched:
            table.add_row(
                str(rule.id),
                rule.name,
                str(rule.priority),
                rule.action,
            )
        console.print(table)
        console.print(f"\n[dim]Actions: {result.actions}[/dim]")


@app.command()
def validate(
    rules: list[str] = typer.Argument(..., help="Rule files (JSON or YAML)"),
    schema: str | None = typer.Option(None, "--schema", help=_SCHEMA_HELP),
    config: str | None = typer.Option(None, "--config", help=_CONFIG_HELP),
    trust_schema: bool = typer.Option(False, "--trust-schema", help=_TRUST_HELP),
) -> None:
    """Validate rules for structural issues and, with a fact schema, unknown fields.

    Reports empty conditions, duplicate ids, unsupported operators, and every
    field the fact schema lacks. The schema comes from --schema, else the rule
    file's fact_schema, else the config file's. Exits 1 when any issue is found
    and 2 when a rule file or the schema cannot be loaded.
    """
    from fluxrules.domain import Ruleset
    from fluxrules.facts import schema_info
    from fluxrules.services.validation_service import ValidationService

    config_schema = _ConfigSchema(config)
    issues: list[str] = []
    schemas: list[dict[str, str | None]] = []
    for path in rules:
        document, loaded = _read_rules(path)
        prefix = f"{path}: " if len(rules) > 1 else ""
        ruleset = Ruleset(
            group="cli",
            rules=tuple(rule.to_engine_rule() for rule in loaded),
        )
        issues.extend(prefix + issue for issue in ValidationService().validate_ruleset(ruleset))
        resolved = _resolve_schema(schema, document, config_schema, trust_schema)
        if resolved is not None:
            unknown = schema_info(resolved.model).unknown_fields(loaded)
            issues.extend(prefix + error.summary for error in unknown)
        schemas.append(
            {
                "file": path,
                "fact_schema": resolved.spec if resolved else None,
                "source": resolved.source if resolved else None,
            }
        )
    console.print_json(data={"valid": not issues, "issues": issues, "schemas": schemas})
    if issues:
        raise typer.Exit(code=1)


@app.command()
def serve(
    host: str = typer.Option("0.0.0.0", help="Bind host"),  # noqa: S104 - servers bind all interfaces by design
    port: int = typer.Option(8000, help="Bind port"),
    reload: bool = typer.Option(False, help="Enable auto-reload"),
) -> None:
    """Start the FluxRules API server (needs the api extra)."""
    try:
        import uvicorn

        from fluxrules.api.app import create_app
    except ImportError:
        console.print("[red]fluxrules[api] not installed. Run: pip install fluxrules[api][/red]")
        raise typer.Exit(1)

    if reload:
        # uvicorn reload requires a string import path, not an app instance
        uvicorn.run(
            "fluxrules.api.app:create_app",
            host=host,
            port=port,
            reload=reload,
            factory=True,
        )
    else:
        uvicorn.run(create_app(), host=host, port=port)


@app.command()
def init(
    dir: str = typer.Option(".", help="Directory to scaffold"),
) -> None:
    """Scaffold a new FluxRules project."""
    target = Path(dir)
    target.mkdir(parents=True, exist_ok=True)

    rules_file = target / "rules.json"
    if not rules_file.exists():
        rules_file.write_text(
            json.dumps(
                [
                    {
                        "id": "1",
                        "name": "high_value_order",
                        "priority": 10,
                        "conditions": {
                            "type": "condition",
                            "field": "amount",
                            "op": ">",
                            "value": 1000,
                        },
                        "action": "flag_for_review",
                        "enabled": True,
                    }
                ],
                indent=2,
            )
            + "\n"
        )
        console.print(f"[green]Created {rules_file}[/green]")

    input_file = target / "input.json"
    if not input_file.exists():
        input_file.write_text(json.dumps({"amount": 1500, "currency": "USD"}, indent=2) + "\n")
        console.print(f"[green]Created {input_file}[/green]")

    config_file = target / "fluxrules.yaml"
    if not config_file.exists():
        config_file.write_text(
            "# FluxRules configuration\n"
            "strict_null_handling: false\n"
            "strict_type_comparison: false\n"
            "boolean_string_coercion: false\n"
            "use_optimized_engine: true\n"
            "# Fact schema that `fluxrules validate` and `evaluate` check rule fields\n"
            "# against: 'package.module:Class' or 'path/to/models.py:Class'.\n"
            "# fact_schema: myapp.models:Order\n"
        )
        console.print(f"[green]Created {config_file}[/green]")

    console.print("\n[bold]Project scaffolded![/bold] Try:")
    console.print(f"  fluxrules evaluate {rules_file} {input_file}")
    console.print(f"  fluxrules validate {rules_file}")


@app.command()
def version() -> None:
    """Print version."""
    from fluxrules.version import __version__

    console.print(f"fluxrules {__version__}")


if __name__ == "__main__":
    app()
