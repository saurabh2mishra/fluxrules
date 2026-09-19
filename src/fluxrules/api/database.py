"""Database engine/session initialization utilities."""

import logging
import os
from collections.abc import Generator
from typing import Any

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from fluxrules.api.config import settings

logger = logging.getLogger("fluxrules.api.database")


def _build_engine(database_url: str) -> Engine:
    connect_args: dict[str, Any] = {}
    if "sqlite" in database_url:
        connect_args["check_same_thread"] = False

    db_engine = create_engine(
        database_url,
        connect_args=connect_args,
        pool_pre_ping=True,
    )

    if "sqlite" in database_url:

        @event.listens_for(db_engine, "connect")
        def set_sqlite_pragma(dbapi_connection: Any, connection_record: Any) -> None:
            del connection_record
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA synchronous=NORMAL")
            cursor.execute("PRAGMA cache_size=-64000")
            cursor.execute("PRAGMA temp_store=MEMORY")
            cursor.execute("PRAGMA mmap_size=268435456")
            cursor.close()

    return db_engine


def _create_engine_with_fallback() -> Engine:
    preferred_url = settings.DATABASE_URL
    fallback_url = "sqlite:///./rule_engine.db"
    env = os.getenv("FLUXRULES_ENV", settings.FLUXRULES_ENV).lower()

    try:
        preferred_engine = _build_engine(preferred_url)
        with preferred_engine.connect() as conn:
            conn.exec_driver_sql("SELECT 1")
        return preferred_engine
    except Exception as exc:
        if "sqlite" in preferred_url:
            raise

        if not settings.DB_FALLBACK_ENABLED:
            raise RuntimeError(
                f"FATAL: Primary database is unreachable ({exc!r}) and DB_FALLBACK_ENABLED is False."
            ) from exc

        if env == "production":
            logger.error(
                "Primary database is unreachable in PRODUCTION and "
                "DB_FALLBACK_ENABLED is True. Falling back to local SQLite."
            )
        else:
            logger.warning(
                "Primary database unreachable; falling back to local SQLite (%s).",
                fallback_url,
            )

        fallback_engine = _build_engine(fallback_url)
        with fallback_engine.connect() as conn:
            conn.exec_driver_sql("SELECT 1")
        return fallback_engine


engine = _create_engine_with_fallback()
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    """Declarative base for all ORM models."""


def _find_alembic_ini() -> str | None:
    """Search for ``alembic.ini`` starting from cwd upward."""
    from pathlib import Path

    for candidate in (Path.cwd(), Path(__file__).resolve().parents[3]):
        ini = candidate / "alembic.ini"
        if ini.is_file():
            return str(ini)
    return None


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    """Create database tables, enforce schema versioning, and optionally seed admin.

    If ``alembic.ini`` is found at the project root the schema is applied via
    Alembic migrations (``alembic upgrade head``).  Otherwise we fall back to
    the classic ``Base.metadata.create_all()`` path so that non-Alembic
    deployments keep working.
    """
    import fluxrules.api.models  # noqa: F401
    from fluxrules.api.schema_manager import validate_schema_version
    from fluxrules.api.security import generate_secure_secret

    _alembic_ini = _find_alembic_ini()
    if _alembic_ini is not None:
        try:
            from alembic.command import upgrade
            from alembic.config import Config

            cfg = Config(_alembic_ini)
            upgrade(cfg, "head")
            logger.info("Database schema applied via Alembic migrations.")
        except Exception:
            logger.exception("Alembic migration failed - falling back to SQLAlchemy create_all.")
            Base.metadata.create_all(bind=engine)
    else:
        Base.metadata.create_all(bind=engine)

    validate_schema_version(engine, settings.SCHEMA_VERSION)

    if not settings.SEED_ADMIN_USER:
        logger.info("Admin user seeding is disabled (SEED_ADMIN_USER=false).")
        return

    db = SessionLocal()
    try:
        from fluxrules.api.models.user import User
        from fluxrules.api.services.auth_service import get_password_hash

        admin = db.query(User).filter(User.username == "admin").first()
        if not admin:
            env = os.getenv("FLUXRULES_ENV", "development").lower()
            password = settings.ADMIN_DEFAULT_PASSWORD

            if not password:
                if env == "production":
                    raise RuntimeError(
                        "FATAL: ADMIN_DEFAULT_PASSWORD must be set in production when SEED_ADMIN_USER is enabled."
                    )
                password = generate_secure_secret(24)
                logger.warning(
                    "Auto-generated admin password for this session: %s",
                    password,
                )

            admin = User(
                username="admin",
                email="admin@example.com",
                hashed_password=get_password_hash(password),
                role="admin",
                is_active=True,
            )
            db.add(admin)
            db.commit()
            logger.info("Seeded default admin user.")
    finally:
        db.close()
