"""Schema version tracking and Alembic migration-safety utilities."""

import logging
from datetime import datetime, timezone

from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine

logger = logging.getLogger("fluxrules.api.schema_manager")

_META_TABLE_NAME = "schema_meta"


def _ensure_meta_table(engine: Engine) -> None:
    insp = inspect(engine)
    if not insp.has_table(_META_TABLE_NAME):
        with engine.begin() as conn:
            conn.execute(
                text(
                    f"""CREATE TABLE IF NOT EXISTS {_META_TABLE_NAME} (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    version VARCHAR NOT NULL,
                    applied_at TIMESTAMP,
                    description VARCHAR DEFAULT ''
                )"""
                )
            )


def get_alembic_version(engine: Engine) -> str | None:
    insp = inspect(engine)
    if not insp.has_table("alembic_version"):
        return None
    with engine.connect() as conn:
        row = conn.execute(text("SELECT version_num FROM alembic_version LIMIT 1")).first()
    return row[0] if row else None


def get_recorded_version(engine: Engine) -> str | None:
    _ensure_meta_table(engine)
    with engine.connect() as conn:
        row = conn.execute(
            text(f"SELECT version FROM {_META_TABLE_NAME} ORDER BY id DESC LIMIT 1")  # noqa: S608 - internal table-name constant, not user input
        ).first()
    if row:
        return row[0]
    return get_alembic_version(engine)


def stamp_version(engine: Engine, version: str, description: str = "") -> None:
    _ensure_meta_table(engine)
    now = datetime.now(timezone.utc).isoformat()
    with engine.begin() as conn:
        conn.execute(
            text(
                f"INSERT INTO {_META_TABLE_NAME} (version, applied_at, description) "  # noqa: S608 - internal table-name constant, not user input
                f"VALUES (:version, :applied_at, :description)"
            ),
            {
                "version": version,
                "applied_at": now,
                "description": description or "initial",
            },
        )
    logger.info("Schema version stamped: %s (%s)", version, description or "initial")


def validate_schema_version(engine: Engine, expected: str) -> None:
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
    _ensure_meta_table(engine)
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                f"SELECT version, applied_at, description FROM {_META_TABLE_NAME} ORDER BY id DESC"  # noqa: S608 - internal table-name constant, not user input
            )
        ).fetchall()
    return [
        {
            "version": r[0],
            "applied_at": r[1] if r[1] else None,
            "description": r[2] or "",
        }
        for r in rows
    ]
