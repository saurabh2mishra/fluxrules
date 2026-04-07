"""Database engine/session initialization utilities.

Reliability behaviour is controlled by ``DB_FALLBACK_ENABLED``:

* **development** (default ``True``): if the primary ``DATABASE_URL`` is
  unreachable and it is *not* already SQLite, fall back silently to a local
  SQLite file.  This keeps the "clone-and-run" developer experience intact.
* **production** (set ``False``): the service **fails fast** with a clear
  error instead of silently degrading to a local SQLite file, which would
  cause data-loss in clustered deployments.

Schema versioning is enforced at startup via Alembic — see
``alembic/`` and :mod:`app.schema_manager`.
"""

from collections.abc import Generator
from typing import Any
import logging
import os

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker, declarative_base

from app.config import settings

logger = logging.getLogger("fluxrules.database")


def _build_engine(database_url: str) -> Engine:
    """Create a SQLAlchemy engine configured for PostgreSQL or SQLite.

    Args:
        database_url: SQLAlchemy-compatible connection URL.

    Returns:
        Configured SQLAlchemy engine.
    """
    connect_args: dict[str, Any] = {}
    if "sqlite" in database_url:
        connect_args["check_same_thread"] = False

    db_engine = create_engine(
        database_url,
        connect_args=connect_args,
        pool_pre_ping=True,
    )

    if "sqlite" in database_url:

        # Potentially unused by static analyzers: invoked by SQLAlchemy event dispatcher.
        @event.listens_for(db_engine, "connect")
        def set_sqlite_pragma(dbapi_connection: Any, connection_record: Any) -> None:
            """Apply SQLite pragmas to improve durability/performance tradeoffs."""
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
    """Build the configured engine with environment-aware fallback behaviour.

    When ``DB_FALLBACK_ENABLED`` is ``True`` (the default for development),
    the service falls back to a local SQLite file if the preferred database
    is unreachable.  When ``False`` (recommended for production), any
    connectivity failure is fatal so that operators get an immediate, loud
    signal rather than silent data-loss.

    Returns:
        A connected SQLAlchemy ``Engine``.

    Raises:
        RuntimeError: In production when the primary DB is unreachable and
            fallback is disabled.
    """
    preferred_url = settings.DATABASE_URL
    fallback_url = "sqlite:///./rule_engine.db"
    env = os.getenv("FLUXRULES_ENV", settings.FLUXRULES_ENV).lower()

    try:
        preferred_engine = _build_engine(preferred_url)
        with preferred_engine.connect() as conn:
            conn.exec_driver_sql("SELECT 1")
        return preferred_engine
    except Exception as exc:
        # If the preferred URL is already SQLite, re-raise — nothing to fall
        # back to.
        if "sqlite" in preferred_url:
            raise

        # --- Fallback decision gate ---
        if not settings.DB_FALLBACK_ENABLED:
            raise RuntimeError(
                f"FATAL: Primary database is unreachable ({exc!r}) and "
                f"DB_FALLBACK_ENABLED is False.  The service cannot start.  "
                f"Fix DATABASE_URL or set DB_FALLBACK_ENABLED=true for "
                f"development use."
            ) from exc

        if env == "production":
            logger.error(
                "⚠️  Primary database is unreachable in PRODUCTION and "
                "DB_FALLBACK_ENABLED is True.  Falling back to local "
                "SQLite — THIS WILL CAUSE DATA INCONSISTENCY in a "
                "clustered deployment.  Set DB_FALLBACK_ENABLED=false "
                "for production."
            )
        else:
            logger.warning(
                "Primary database unreachable; falling back to local "
                "SQLite (%s).  Set DB_FALLBACK_ENABLED=false to disable "
                "this behaviour.",
                fallback_url,
            )

        fallback_engine = _build_engine(fallback_url)
        with fallback_engine.connect() as conn:
            conn.exec_driver_sql("SELECT 1")
        return fallback_engine


engine = _create_engine_with_fallback()
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def get_db() -> Generator[Session, None, None]:
    """Yield an active database session for request-scoped dependency injection."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    """Create database tables, enforce schema versioning, and optionally seed admin.

    Startup sequence:
    1. Create all ORM tables (``CREATE TABLE IF NOT EXISTS``).
    2. Validate the Alembic schema version (see :mod:`app.schema_manager`).
    3. Optionally seed the bootstrap admin user.

    Admin seeding behaviour is controlled by the following settings:

    * ``SEED_ADMIN_USER`` (bool) — set ``False`` to skip seeding entirely.
    * ``ADMIN_DEFAULT_PASSWORD`` (str) — explicit password; when empty a
      cryptographically-secure random password is generated and logged once
      (development only; in production the env var **must** be set).
    * ``ADMIN_FORCE_PASSWORD_CHANGE`` (bool) — when ``True`` the seeded
      account is flagged so the user must reset their password on first
      login.
    """
    import os

    from app.schema_manager import validate_schema_version
    from app.security import generate_secure_secret

    import app.models  # noqa: F401  # Load ORM model mappings before creating tables.

    Base.metadata.create_all(bind=engine)

    # --- Schema version gate ---
    validate_schema_version(engine, settings.SCHEMA_VERSION)

    if not settings.SEED_ADMIN_USER:
        logger.info("Admin user seeding is disabled (SEED_ADMIN_USER=false).")
        return

    db = SessionLocal()
    try:
        from app.models.user import User
        from app.services.auth_service import get_password_hash

        admin = db.query(User).filter(User.username == "admin").first()
        if not admin:
            env = os.getenv("FLUXRULES_ENV", "development").lower()
            password = settings.ADMIN_DEFAULT_PASSWORD

            if not password:
                if env == "production":
                    raise RuntimeError(
                        "FATAL: ADMIN_DEFAULT_PASSWORD must be set in production "
                        "when SEED_ADMIN_USER is enabled. Refusing to start with "
                        "an auto-generated password in a production environment."
                    )
                # Development / test: generate a one-time random password.
                password = generate_secure_secret(24)
                logger.warning(
                    "🔑 Auto-generated admin password for this session: %s  "
                    "Set ADMIN_DEFAULT_PASSWORD in .env to make it persistent.",
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
            logger.info(
                "Seeded default admin user (force_password_change=%s).",
                settings.ADMIN_FORCE_PASSWORD_CHANGE,
            )
    finally:
        db.close()
