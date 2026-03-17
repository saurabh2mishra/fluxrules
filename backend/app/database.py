"""Database engine/session initialization utilities."""

from collections.abc import Generator
from typing import Any

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import Session, sessionmaker

from app.config import settings


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
    """Build the configured engine and fallback to local SQLite when unavailable."""
    preferred_url = settings.DATABASE_URL
    fallback_url = "sqlite:///./rule_engine.db"

    try:
        preferred_engine = _build_engine(preferred_url)
        with preferred_engine.connect() as conn:
            conn.exec_driver_sql("SELECT 1")
        return preferred_engine
    except Exception:
        if "sqlite" in preferred_url:
            raise
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
    """Create database tables and seed default admin credentials if missing."""
    Base.metadata.create_all(bind=engine)

    db = SessionLocal()
    from app.models.user import User
    from app.services.auth_service import get_password_hash

    admin = db.query(User).filter(User.username == "admin").first()
    if not admin:
        admin = User(
            username="admin",
            email="admin@example.com",
            hashed_password=get_password_hash("admin123"),
            role="admin",
            is_active=True,
        )
        db.add(admin)
        db.commit()

    db.close()
