"""Tests for Alembic migration integration."""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

# Project root (where alembic.ini lives)
_ROOT = Path(__file__).resolve().parents[2]
_ALEMBIC_INI = str(_ROOT / "alembic.ini")


def _make_cfg(db_path: str):
    from alembic.config import Config

    cfg = Config(_ALEMBIC_INI)
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db_path}")
    # Ensure script_location is absolute so it works regardless of CWD
    cfg.set_main_option("script_location", str(_ROOT / "alembic"))
    return cfg


@pytest.fixture()
def fresh_db(tmp_path):
    """Yield a path to a fresh SQLite database file."""
    db_file = tmp_path / "test_alembic.db"
    yield str(db_file)


#  Feature 1 - Alembic tests


class TestAlembicMigrations:
    """Verify Alembic migration infrastructure."""

    def test_alembic_ini_exists(self):
        """alembic.ini must exist at the project root."""
        assert os.path.isfile(_ALEMBIC_INI)

    def test_alembic_env_exists(self):
        """alembic/env.py must exist."""
        assert os.path.isfile(str(_ROOT / "alembic" / "env.py"))

    def test_initial_migration_exists(self):
        """An initial migration file must exist."""
        versions_dir = _ROOT / "alembic" / "versions"
        assert versions_dir.is_dir()
        py_files = [f for f in os.listdir(versions_dir) if f.endswith(".py")]
        assert len(py_files) >= 1, "At least one migration file expected"

    def test_initial_migration_creates_tables(self, fresh_db):
        """Running upgrade head should create all expected tables."""
        from alembic.command import upgrade

        cfg = _make_cfg(fresh_db)
        upgrade(cfg, "head")

        engine = create_engine(f"sqlite:///{fresh_db}")
        inspector = inspect(engine)
        tables = set(inspector.get_table_names())
        expected = {
            "users",
            "rules",
            "rule_versions",
            "audit_logs",
            "audit_policies",
            "audit_reports",
            "conflicted_rules",
            "alembic_version",
        }
        assert expected.issubset(tables), f"Missing tables: {expected - tables}"

    def test_downgrade_removes_tables(self, fresh_db):
        """Downgrade to base should remove application tables."""
        from alembic.command import downgrade, upgrade

        cfg = _make_cfg(fresh_db)
        upgrade(cfg, "head")
        downgrade(cfg, "base")

        engine = create_engine(f"sqlite:///{fresh_db}")
        inspector = inspect(engine)
        tables = set(inspector.get_table_names()) - {"alembic_version"}
        assert len(tables) == 0, f"Tables remain after downgrade: {tables}"

    def test_upgrade_downgrade_upgrade_idempotent(self, fresh_db):
        """upgrade -> downgrade -> upgrade should be idempotent."""
        from alembic.command import downgrade, upgrade

        cfg = _make_cfg(fresh_db)
        upgrade(cfg, "head")
        downgrade(cfg, "base")
        upgrade(cfg, "head")

        engine = create_engine(f"sqlite:///{fresh_db}")
        tables = set(inspect(engine).get_table_names())
        assert "rules" in tables
        assert "users" in tables

    def test_alembic_version_table_created(self, fresh_db):
        """alembic_version table should contain a revision after upgrade."""
        from alembic.command import upgrade

        cfg = _make_cfg(fresh_db)
        upgrade(cfg, "head")

        engine = create_engine(f"sqlite:///{fresh_db}")
        with engine.connect() as conn:
            row = conn.execute(text("SELECT version_num FROM alembic_version")).first()
        assert row is not None
        assert row[0] == "001_initial"


class TestInitDbFallback:
    """Verify init_db() still works without alembic.ini."""

    def test_init_db_creates_tables_without_alembic(self, monkeypatch):
        """init_db() falls back to SQLAlchemy when alembic.ini is absent."""
        from fluxrules.api import database as db_mod

        monkeypatch.setattr(db_mod, "_find_alembic_ini", lambda: None)

        engine = create_engine(
            "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
        )
        monkeypatch.setattr(db_mod, "engine", engine)
        monkeypatch.setattr(db_mod, "SessionLocal", sessionmaker(bind=engine))

        # Disable admin seeding for simplicity
        from fluxrules.api.config import settings

        monkeypatch.setattr(settings, "SEED_ADMIN_USER", False)

        db_mod.init_db()

        tables = set(inspect(engine).get_table_names())
        assert "rules" in tables
        assert "users" in tables
