"""Saved evaluation results keep their comparison issues.

``ExecutionRepository`` saves each evaluation to ``evaluation_results``, and
``explain()`` reads it back after the in-memory result is gone. Migration 003
adds the ``comparison_issues`` column, creating the table when a database does
not have it yet.
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("alembic")
pytest.importorskip("sqlalchemy")

from sqlalchemy import create_engine, inspect, text  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

from fluxrules.domain.comparison_issues import ComparisonIssue  # noqa: E402
from fluxrules.domain.models import EvaluationResult  # noqa: E402

_ROOT = Path(__file__).resolve().parents[2]
ISSUE = ComparisonIssue("amount", ">", "str", "int", "these types cannot be ordered")


def _cfg(db: Path):
    from alembic.config import Config

    cfg = Config(str(_ROOT / "alembic.ini"))
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db}")
    cfg.set_main_option("script_location", str(_ROOT / "alembic"))
    return cfg


def _columns(db: Path) -> set[str]:
    engine = create_engine(f"sqlite:///{db}")
    return {c["name"] for c in inspect(engine).get_columns("evaluation_results")}


def test_the_repository_saves_and_loads_the_issues():
    from fluxrules.api.database import Base
    from fluxrules.persistence.execution_repository import ExecutionRepository

    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    repository = ExecutionRepository(session)
    repository.save(
        EvaluationResult(
            execution_id="e1", ruleset_group="g", fired_rules=[1], comparison_issues=[ISSUE]
        )
    )
    repository.save(EvaluationResult(execution_id="e2", ruleset_group="g", fired_rules=[]))
    assert repository.load("e1").comparison_issues == [ISSUE]
    assert repository.load("e2").comparison_issues == []


def test_upgrade_creates_the_table_with_the_column(tmp_path: Path):
    from alembic.command import upgrade

    db = tmp_path / "fresh.db"
    upgrade(_cfg(db), "head")
    assert "comparison_issues" in _columns(db)


def test_upgrade_adds_the_column_and_keeps_saved_rows(tmp_path: Path):
    from alembic.command import upgrade

    db = tmp_path / "old.db"
    cfg = _cfg(db)
    upgrade(cfg, "002_rename_conditions")
    engine = create_engine(f"sqlite:///{db}")
    # The table as create_all made it before 1.2.0.
    with engine.begin() as conn:
        conn.execute(
            text(
                "CREATE TABLE evaluation_results (id INTEGER PRIMARY KEY, "
                "execution_id VARCHAR NOT NULL UNIQUE, ruleset_id VARCHAR, "
                "fired_rules TEXT NOT NULL, actions TEXT NOT NULL, trace TEXT NOT NULL, "
                "created_at DATETIME NOT NULL)"
            )
        )
        conn.execute(
            text(
                "INSERT INTO evaluation_results (execution_id, fired_rules, actions, trace, "
                "created_at) VALUES ('old', '[1]', '[]', '[]', '2026-01-01')"
            )
        )
    upgrade(cfg, "head")
    assert "comparison_issues" in _columns(db)
    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT fired_rules, comparison_issues FROM evaluation_results")
        ).one()
    assert tuple(row) == ("[1]", "[]")


def test_downgrade_drops_the_table(tmp_path: Path):
    from alembic.command import downgrade, upgrade

    db = tmp_path / "down.db"
    cfg = _cfg(db)
    upgrade(cfg, "head")
    downgrade(cfg, "002_rename_conditions")
    engine = create_engine(f"sqlite:///{db}")
    assert not inspect(engine).has_table("evaluation_results")
