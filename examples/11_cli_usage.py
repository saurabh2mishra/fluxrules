"""Batch 2 example: the fluxrules command-line tool.

Installing ``fluxrules[cli]`` adds a ``fluxrules`` command. It works on JSON
files, so it fits scripts and CI jobs:

    fluxrules validate rules.json
    fluxrules evaluate rules.json fact.json --format json

This example writes the shared rules and one fact to a temporary directory and
runs those two commands in-process with Typer's ``CliRunner``, printing exactly
what the shell would show.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from shared_use_case import SHARED_FACTS, USE_CASE_NAME, build_shared_rules

try:
    from typer.testing import CliRunner

    from fluxrules.cli.main import app
except ImportError:  # pragma: no cover - depends on installed extras
    raise SystemExit("This example needs the CLI extra: pip install 'fluxrules[cli]'") from None


def main() -> None:
    print("=" * 80)
    print("11_cli_usage.py")
    print(f"Use case: {USE_CASE_NAME}")
    print("=" * 80)

    runner = CliRunner()
    with tempfile.TemporaryDirectory() as tmp:
        rules_file = Path(tmp) / "rules.json"
        fact_file = Path(tmp) / "fact.json"
        rules = [rule.model_dump(mode="json") for rule in build_shared_rules()]
        rules_file.write_text(json.dumps(rules, indent=2))
        fact_file.write_text(json.dumps(SHARED_FACTS[0], indent=2))

        for args in (
            ["validate", str(rules_file)],
            ["evaluate", str(rules_file), str(fact_file), "--format", "json"],
        ):
            shown = " ".join(a if not a.startswith(tmp) else Path(a).name for a in args)
            print(f"\n$ fluxrules {shown}")
            result = runner.invoke(app, args)
            print(result.output.rstrip())
            print(f"(exit code {result.exit_code})")


if __name__ == "__main__":
    main()
