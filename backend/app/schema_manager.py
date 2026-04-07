"""Schema version tracking and Alembic migration-safety utilities.

This module provides lightweight schema-version bookkeeping that integrates
with Alembic's ``alembic_version`` table.  It ensures the running code and
the underlying database are in agreement at startup.

For **new deployments**, the service auto-stamps the expected version.
For **existing deployments**, operators must run ``alembic upgrade head``
before restarting after a schema change.

The version identifier is a short string (e.g. ``"001"``) that maps 1-to-1
with Alembic revision IDs recorded in ``migrations/versions/``.
"""

import logging
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import Column, DateTime, Integer, String, Table, text, inspect
from sqlalchemy.engine import Engine

logger = logging.getLogger("fluxrules.schema_manager")


# ---------------------------------------------------------------------------
# schema_meta table — extended history beyond Alembic's single-row tracker
# ---------------------------------------------------------------------------

_META_TABLE_NAME = "schema_meta"


def _ensure_meta_table(engine: Engine) -> None:
    """Create the ``schema_meta`` table if it does not yet exist.

    This is a lightweight history table that records every schema version
    stamp with a timestamp and description, complementing Alembic's
    single-row ``alembic_version`` table.

    Args:
        engine: Active SQLAlchemy engine.
    """
    insp = inspect(engine)
    if not insp.has_table(_META_TABLE_NAME):
        with engine.begin() as conn:
            conn.execute(text(
                f"""CREATE TABLE IF NOT EXISTS {_META_TABLE_NAME} (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    version VARCHAR NOT NULL,
                    applied_at TIMESTAMP,
                    description VARCHAR DEFAULT ''
                )"""
            ))


def get_alembic_version(engine: Engine) -> Optional[str]:
    """Return the Alembic revision stored in ``alembic_version``, or ``None``.

    Args:
        engine: Active SQLAlchemy engine.

    Returns:
        The revision string, or ``None`` when the table doesn't exist or is empty.
    """
    insp = inspect(engine)
    if not insp.has_table("alembic_version"):
        return None
    with engine.connect() as conn:
        row = conn.execute(text("SELECT version_num FROM alembic_version LIMIT 1")).first()
    return row[0] if row else None


def get_recorded_version(engine: Engine) -> Optional[str]:
    """Return the latest schema version from ``schema_meta``, or ``None``.

    Falls back to the Alembic version if schema_meta is empty.

    Args:
        engine: Active SQLAlchemy engine.

    Returns:
        The version string, or ``None`` when no version is recorded.
    """
    _ensure_meta_table(engine)
    with engine.connect() as conn:
        row = conn.execute(
            text(f"SELECT version FROM {_META_TABLE_NAME} ORDER BY id DESC LIMIT 1")
        ).first()
    if row:
        return row[0]
    # Fallback: check alembic_version
    return get_alembic_version(engine)


def stamp_version(engine: Engine, version: str, description: str = "") -> None:
    """Write a new schema-version row to ``schema_meta``.

    This is called during ``init_db()`` on first startup or after a migration.

    Args:
        engine: Active SQLAlchemy engine.
        version: The schema version to record.
        description: Free-text migration note.
    """
    _ensure_meta_table(engine)
    now = datetime.now(timezone.utc).isoformat()
    with engine.begin() as conn:
        conn.execute(
            text(
                f"INSERT INTO {_META_TABLE_NAME} (version, applied_at, description) "
                f"VALUES (:version, :applied_at, :description)"
            ),
            {"version": version, "applied_at": now, "description": description or "initial"},
        )
    logger.info("Schema version stamped: %s (%s)", version, description or "initial")


def validate_schema_version(engine: Engine, expected: str) -> None:
    """Compare the recorded schema version against the expected version.

    Behaviour:
    * If no version is recorded yet (fresh database), stamp the current
      expected version and return.
    * If the recorded version matches, return silently.
    * If there is a mismatch, raise ``RuntimeError`` so the service fails
      fast instead of running against an incompatible schema.

    Args:
        engine: Active SQLAlchemy engine.
        expected: ``settings.SCHEMA_VERSION``.

    Raises:
        RuntimeError: When recorded ≠ expected.
    """
    recorded = get_recorded_version(engine)

    if recorded is None:
        stamp_version(engine, expected, "initial schema")
        return

    if recorded == expected:
        logger.debug("Schema version OK: %s", recorded)
        return

    raise RuntimeError(
        f"Schema version mismatch: database has v{recorded} but the "
        f"application expects v{expected}. Run 'alembic upgrade head' "
        f"before starting the service."
    )


def get_version_history(engine: Engine) -> list[dict]:
    """Return all recorded schema versions ordered newest-first.

    Args:
        engine: Active SQLAlchemy engine.

    Returns:
        List of ``{"version": str, "applied_at": str, "description": str}``
        dicts.
    """
    _ensure_meta_table(engine)
    with engine.connect() as conn:
        rows = conn.execute(
            text(f"SELECT version, applied_at, description FROM {_META_TABLE_NAME} ORDER BY id DESC")
        ).fetchall()
    return [
        {
            "version": r[0],
            "applied_at": r[1] if r[1] else None,
            "description": r[2] or "",
        }
        for r in rows
    ]
