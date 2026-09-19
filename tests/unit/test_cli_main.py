"""Unit tests for the ``fluxrules`` CLI (Typer app).

Drives the CLI through Typer's ``CliRunner`` to cover ``version``, ``init``
scaffolding, ``validate``, and ``evaluate`` in both table and JSON output modes,
plus the rule-loading helper and error paths.
"""

from __future__ import annotations

import json
import sys
import types
from pathlib import Path

import pytest
from typer.testing import CliRunner

from fluxrules.cli.main import _load_rules, app

runner = CliRunner()

_RULE = {
    "name": "high_value",
    "priority": 10,
    "condition_dsl": {"type": "condition", "field": "amount", "op": ">", "value": 1000},
    "action": "flag_for_review",
    "enabled": True,
}


def _write_json(path: Path, data: object) -> Path:
    path.write_text(json.dumps(data))
    return path


def test_version_prints_package_version() -> None:
    from fluxrules.version import __version__

    result = runner.invoke(app, ["version"])
    assert result.exit_code == 0
    assert __version__ in result.stdout


def test_load_rules_accepts_single_mapping(tmp_path: Path) -> None:
    rules_file = _write_json(tmp_path / "rules.json", _RULE)
    loaded = _load_rules(str(rules_file))
    assert len(loaded) == 1
    assert loaded[0].name == "high_value"


def test_load_rules_accepts_list(tmp_path: Path) -> None:
    rules_file = _write_json(tmp_path / "rules.json", [_RULE, {**_RULE, "name": "other"}])
    loaded = _load_rules(str(rules_file))
    assert [r.name for r in loaded] == ["high_value", "other"]


def test_init_scaffolds_project_files(tmp_path: Path) -> None:
    result = runner.invoke(app, ["init", "--dir", str(tmp_path)])
    assert result.exit_code == 0
    assert (tmp_path / "rules.json").exists()
    assert (tmp_path / "input.json").exists()
    assert (tmp_path / "fluxrules.yaml").exists()
    # The scaffolded rules must be valid JSON matching the documented schema.
    rules = json.loads((tmp_path / "rules.json").read_text())
    assert rules[0]["name"] == "high_value_order"


def test_init_is_idempotent_and_does_not_overwrite(tmp_path: Path) -> None:
    (tmp_path / "rules.json").write_text('{"custom": true}')
    result = runner.invoke(app, ["init", "--dir", str(tmp_path)])
    assert result.exit_code == 0
    # Existing file is preserved, not clobbered by the scaffold.
    assert json.loads((tmp_path / "rules.json").read_text()) == {"custom": True}


def test_init_skips_all_existing_files(tmp_path: Path) -> None:
    # Pre-create every scaffold target so init takes each "skip" branch.
    (tmp_path / "rules.json").write_text("[]")
    (tmp_path / "input.json").write_text("{}")
    (tmp_path / "fluxrules.yaml").write_text("# existing\n")
    result = runner.invoke(app, ["init", "--dir", str(tmp_path)])
    assert result.exit_code == 0
    assert (tmp_path / "input.json").read_text() == "{}"
    assert (tmp_path / "fluxrules.yaml").read_text() == "# existing\n"


def test_serve_reload_uses_import_string(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[tuple, dict]] = []
    fake_uvicorn = types.ModuleType("uvicorn")
    fake_uvicorn.run = lambda *a, **k: calls.append((a, k))  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "uvicorn", fake_uvicorn)

    result = runner.invoke(app, ["serve", "--reload", "--port", "9001"])
    assert result.exit_code == 0
    assert len(calls) == 1
    args, kwargs = calls[0]
    # reload path must pass the import string + factory=True, not an app instance.
    assert args[0] == "fluxrules.api.app:create_app"
    assert kwargs["reload"] is True
    assert kwargs["factory"] is True
    assert kwargs["port"] == 9001


def test_serve_without_reload_builds_app(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[tuple, dict]] = []
    fake_uvicorn = types.ModuleType("uvicorn")
    fake_uvicorn.run = lambda *a, **k: calls.append((a, k))  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "uvicorn", fake_uvicorn)

    fake_app_module = types.ModuleType("fluxrules.api.app")
    sentinel = object()
    fake_app_module.create_app = lambda: sentinel  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "fluxrules.api.app", fake_app_module)

    result = runner.invoke(app, ["serve", "--host", "127.0.0.1", "--port", "9002"])
    assert result.exit_code == 0
    assert len(calls) == 1
    args, kwargs = calls[0]
    assert args[0] is sentinel  # non-reload passes the built app instance
    assert kwargs["port"] == 9002


def test_serve_without_api_extra_exits_with_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Simulate fluxrules[api] not being installed: importing uvicorn fails.
    monkeypatch.setitem(sys.modules, "uvicorn", None)
    result = runner.invoke(app, ["serve"])
    assert result.exit_code == 1


def test_validate_reports_clean_ruleset(tmp_path: Path) -> None:
    rules_file = _write_json(tmp_path / "rules.json", [_RULE])
    result = runner.invoke(app, ["validate", str(rules_file)])
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["valid"] is True
    assert payload["issues"] == []


def test_evaluate_json_output_reports_matched_rule(tmp_path: Path) -> None:
    rules_file = _write_json(tmp_path / "rules.json", [_RULE])
    input_file = _write_json(tmp_path / "input.json", {"amount": 1500})

    result = runner.invoke(app, ["evaluate", str(rules_file), str(input_file), "--format", "json"])
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["matched_rules"][0]["name"] == "high_value"
    assert "flag_for_review" in payload["actions"]


def test_evaluate_table_output_lists_matched_rule(tmp_path: Path) -> None:
    rules_file = _write_json(tmp_path / "rules.json", [_RULE])
    input_file = _write_json(tmp_path / "input.json", {"amount": 1500})

    result = runner.invoke(app, ["evaluate", str(rules_file), str(input_file)])
    assert result.exit_code == 0
    assert "high_value" in result.stdout
    assert "Matched Rules" in result.stdout


def test_evaluate_no_match_yields_empty_actions(tmp_path: Path) -> None:
    rules_file = _write_json(tmp_path / "rules.json", [_RULE])
    input_file = _write_json(tmp_path / "input.json", {"amount": 10})

    result = runner.invoke(app, ["evaluate", str(rules_file), str(input_file), "--format", "json"])
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["matched_rules"] == []
    assert payload["actions"] == []
