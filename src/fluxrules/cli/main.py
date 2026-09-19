"""FluxRules CLI - ``fluxrules`` command-line interface."""

from __future__ import annotations

import json
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

app = typer.Typer(name="fluxrules", help="FluxRules - Business Rule Engine CLI")
console = Console()


def _load_rules(path: str) -> list:
    """Load rules from a JSON file into canonical Rule objects.

    The file holds a single rule mapping or a list of rule mappings using the
    documented rule schema (id, name, priority, condition_dsl, action, enabled).
    """
    from fluxrules.domain import Rule

    with open(path) as f:
        data = json.load(f)
    if not isinstance(data, list):
        data = [data]
    return [Rule(**{**item, "persist": False}) for item in data]


@app.command()
def evaluate(
    rules: str = typer.Argument(..., help="Path to rules JSON file"),
    input: str = typer.Argument(..., help="Path to input/event JSON file"),
    format: str = typer.Option("table", help="Output format: table or json"),
    engine: str = typer.Option("PHREAK", help="Engine to use (any registered engine, e.g. PHREAK)"),
) -> None:
    """Evaluate an event against rules."""
    from fluxrules.engine import get_available_engines, get_engine

    if engine.upper() not in {name.upper() for name in get_available_engines()}:
        available = ", ".join(get_available_engines())
        console.print(f"[red]Unknown engine '{engine}'. Available: {available}[/red]")
        raise typer.Exit(code=2)

    loaded = _load_rules(rules)
    rule_engine = get_engine(engine)
    rule_engine.load_rules(loaded)

    with open(input) as f:
        event = json.load(f)

    result = rule_engine.evaluate(event)
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
    rules: str = typer.Argument(..., help="Path to rules JSON file"),
) -> None:
    """Validate rules for structural issues.

    Reports empty conditions, duplicate ids, and unsupported operators.
    """
    from fluxrules.domain import Ruleset
    from fluxrules.services.validation_service import ValidationService

    loaded = _load_rules(rules)
    ruleset = Ruleset(
        group="cli",
        rules=tuple(rule.to_engine_rule() for rule in loaded),
    )
    issues = ValidationService().validate_ruleset(ruleset)
    console.print_json(data={"valid": not issues, "issues": issues})


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
                        "condition_dsl": {
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
