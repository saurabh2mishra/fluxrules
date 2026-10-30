"""FluxRules CLI - ``fluxrules`` command-line interface."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import typer
from rich.console import Console
from rich.table import Table

app = typer.Typer(name="fluxrules", help="FluxRules - Business Rule Engine CLI")
console = Console()
err_console = Console(stderr=True)

# Searched in order for a ``fact_schema`` key when --config is not given.
_CONFIG_LOCATIONS = (
    "fluxrules.yaml",
    "fluxrules.yml",
    "fluxrules.json",
    "config/fluxrules.yaml",
    "config/fluxrules.yml",
    "config/fluxrules.json",
)

_SCHEMA_HELP = (
    "Fact schema to check rule fields against: 'package.module:Class' or "
    "'path/to/models.py:Class'. Overrides a fact_schema in the rule file or config."
)
_CONFIG_HELP = (
    "Config file whose fact_schema key applies when neither --schema nor the rule "
    "file names one. Default: $FLUXRULES_CONFIG_FILE, else ./fluxrules.yaml (or "
    ".yml/.json, or under config/) if present."
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


def _config_schema(config: str | None) -> tuple[str, Path, str] | None:
    """The config file's ``fact_schema``: (import string, its directory, source label)."""
    if config is not None:
        if not Path(config).is_file():
            raise _fail(f"Config file not found: {config}")
        path = Path(config)
    else:
        candidates = [os.getenv("FLUXRULES_CONFIG_FILE") or "", *_CONFIG_LOCATIONS]
        found = next((c for c in candidates if c and Path(c).is_file()), None)
        if found is None:
            return None
        path = Path(found)
    try:
        with open(path) as f:
            if path.suffix.lower() == ".json":
                data = json.load(f)
            else:
                import yaml  # type: ignore[import]

                data = yaml.safe_load(f)
    except (OSError, ImportError, ValueError) as exc:
        raise _fail(f"Cannot read config file {path}: {exc}") from None
    spec = data.get("fact_schema") if isinstance(data, dict) else None
    if spec is None:
        return None
    if not isinstance(spec, str):
        raise _fail(f"{path}: fact_schema must be an import string such as 'myapp.models:Order'")
    return spec, path.parent, f"config {path}"


def _resolve_schema(
    flag: str | None,
    document: Any,
    config_schema: tuple[str, Path, str] | None,
) -> _Schema | None:
    """Pick the schema: --schema, else the rule file's, else the config's."""
    from fluxrules.facts import load_schema

    if flag is not None:
        spec, base, source = flag, Path.cwd(), "--schema"
    elif document.fact_schema is not None:
        spec, base, source = (
            document.fact_schema,
            document.path.parent,
            f"rule file {document.path}",
        )
    elif config_schema is not None:
        spec, base, source = config_schema
    else:
        return None
    try:
        return _Schema(model=load_schema(spec, base_dir=base), spec=spec, source=source)
    except (ImportError, TypeError) as exc:
        raise _fail(f"Cannot load fact schema {spec!r} (from {source}): {exc}") from None


@app.command()
def evaluate(
    rules: str = typer.Argument(..., help="Path to a rules file (JSON or YAML)"),
    input: str = typer.Argument(..., help="Path to input/event JSON file"),
    format: str = typer.Option("table", help="Output format: table or json"),
    engine: str = typer.Option("PHREAK", help="Engine to use (any registered engine, e.g. PHREAK)"),
    schema: str | None = typer.Option(None, "--schema", help=_SCHEMA_HELP),
    config: str | None = typer.Option(None, "--config", help=_CONFIG_HELP),
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
    resolved = _resolve_schema(schema, document, _config_schema(config))
    if validate_facts != "off" and resolved is None:
        raise _fail("--validate-facts needs a fact schema (--schema, or fact_schema in a file)")
    engine_kwargs = (
        {"fact_schema": resolved.model, "validate_facts": validate_facts} if resolved else {}
    )
    rule_engine = get_engine(engine, **engine_kwargs)
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

    config_schema = _config_schema(config)
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
        resolved = _resolve_schema(schema, document, config_schema)
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
    """Start the FluxRules API server (requires fluxrules[api])."""
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
