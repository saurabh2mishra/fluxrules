"""``_parse_xlsx_rules`` with a stubbed ``openpyxl``.

openpyxl is not a project dependency, so the parser is exercised against a
minimal stand-in that mimics ``load_workbook(...).active.iter_rows(values_only=True)``.
"""

from __future__ import annotations

import sys
from types import SimpleNamespace

import pytest

pytest.importorskip("fastapi")

from fluxrules.api.routes.rules import _parse_xlsx_rules  # noqa: E402


def _stub_openpyxl(monkeypatch: pytest.MonkeyPatch, rows: list[tuple]) -> None:
    sheet = SimpleNamespace(iter_rows=lambda values_only: iter(rows))
    fake = SimpleNamespace(load_workbook=lambda *a, **kw: SimpleNamespace(active=sheet))
    monkeypatch.setitem(sys.modules, "openpyxl", fake)


def test_parses_rows_including_short_trailing_cells(monkeypatch: pytest.MonkeyPatch) -> None:
    _stub_openpyxl(
        monkeypatch,
        [
            ("Name", "Action", "Conditions", "Priority"),
            ("r1", "allow", '{"type": "condition", "field": "x", "op": ">", "value": 1}', 5),
            # Shorter than the header row: missing cells read as absent.
            ("r2", "deny", '{"type": "condition", "field": "y", "op": "==", "value": 2}'),
        ],
    )

    rules = _parse_xlsx_rules(b"ignored")

    assert [r["name"] for r in rules] == ["r1", "r2"]
    assert rules[0]["priority"] == 5
    assert rules[1]["priority"] == 0
    assert rules[1]["conditions"]["field"] == "y"
    assert rules[0]["enabled"] is True


def test_missing_required_column_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    _stub_openpyxl(monkeypatch, [("name", "action"), ("r1", "allow")])

    with pytest.raises(ValueError, match="Missing required columns: conditions"):
        _parse_xlsx_rules(b"ignored")
