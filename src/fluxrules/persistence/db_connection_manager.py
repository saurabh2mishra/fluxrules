"""Database connection manager with singleton pattern and lazy initialization.

Provides thread-safe singleton management of SQLAlchemy database sessions
with lazy initialization on first use.
"""

from __future__ import annotations

import logging
from threading import Lock

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from fluxrules.persistence.database_config import DatabaseConfig

logger = logging.getLogger(__name__)


class DBConnectionManager:
    """Singleton database connection manager.

    Usage:
        # During app startup
        config = DatabaseConfig.from_env()
        DBConnectionManager.initialize(config)

        # Anywhere in code
        session = DBConnectionManager.get_session()

    Thread-safe singleton with lazy initialization.
    """

    _instance: DBConnectionManager | None = None
    _lock: Lock = Lock()
    _initialized: bool = False

    def __init__(self, config: DatabaseConfig) -> None:
        """Initialize connection manager.

        Args:
            config: DatabaseConfig instance
        """
        self.config = config
        self._engine = None
        self._session_factory = None
        self._local_session = None

    @classmethod
    def initialize(cls, config: DatabaseConfig | None = None) -> DBConnectionManager:
        """Initialize the singleton database manager.

        Should be called once during application startup.

        Args:
            config: DatabaseConfig instance. If None, loads from environment.

        Returns:
            Singleton DBConnectionManager instance
        """
        if cls._initialized:
            logger.debug("DBConnectionManager already initialized, returning existing instance")
            assert cls._instance is not None
            return cls._instance

        with cls._lock:
            if cls._initialized:
                assert cls._instance is not None
                return cls._instance

            if config is None:
                config = DatabaseConfig.from_env()

            cls._instance = cls(config)
            cls._initialized = True

            logger.info(f"DBConnectionManager initialized with config: env={config.env}")
            return cls._instance

    @classmethod
    def get_instance(cls) -> DBConnectionManager:
        """Get the singleton instance.

        Returns:
            Singleton DBConnectionManager instance
        """
        if cls._instance is None:
            logger.warning(
                "DBConnectionManager not initialized. Calling initialize() with default config."
            )
            return cls.initialize()
        return cls._instance

    def _create_engine(self):
        """Create SQLAlchemy engine with proper configuration."""
        if self._engine is not None:
            return self._engine

        logger.debug(f"Creating SQLAlchemy engine for: {self.config.db_url[:50]}...")

        # Handle SQLite-specific configuration
        if "sqlite" in self.config.db_url:
            from sqlalchemy import event

            # SQLite doesn't support pool_size/max_overflow, use NullPool
            engine = create_engine(
                self.config.db_url,
                echo=self.config.echo_sql,
                connect_args={"check_same_thread": False},  # For SQLite
                poolclass=None,  # Use default pool for SQLite
            )

            # Enable foreign keys for SQLite
            @event.listens_for(engine, "connect")
            def set_sqlite_pragma(dbapi_conn, connection_record):
                cursor = dbapi_conn.cursor()
                cursor.execute("PRAGMA foreign_keys=ON")
                cursor.close()
        else:
            # PostgreSQL or other databases
            engine = create_engine(
                self.config.db_url,
                echo=self.config.echo_sql,
                pool_size=self.config.pool_size,
                max_overflow=self.config.max_overflow,
                pool_recycle=self.config.pool_recycle,
            )

        self._engine = engine
        logger.info("SQLAlchemy engine created successfully")
        return engine

    def _create_session_factory(self):
        """Create SQLAlchemy session factory."""
        if self._session_factory is not None:
            return self._session_factory

        engine = self._create_engine()
        self._session_factory = sessionmaker(bind=engine)
        logger.debug("Session factory created")
        return self._session_factory

    def get_session(self) -> Session:
        """Get a new SQLAlchemy session.

        Uses lazy initialization - engine and factory are created on first call.

        Returns:
            New SQLAlchemy Session instance
        """
        session_factory = self._create_session_factory()
        session = session_factory()
        logger.debug("New session created")
        return session

    def create_all_tables(self) -> None:
        """Create all database tables from SQLAlchemy models.

        Must be called before using the database.
        """
        try:
            engine = self._create_engine()

            # Import Base to create all tables
            from fluxrules.api.database import Base

            logger.info("Creating all database tables...")
            Base.metadata.create_all(engine)
            logger.info("Database tables created successfully")
        except Exception as e:
            logger.error(f"Failed to create database tables: {e}", exc_info=True)
            raise

    def close(self) -> None:
        """Close database connection and cleanup resources."""
        if self._engine is not None:
            logger.info("Closing database engine...")
            self._engine.dispose()
            self._engine = None
            self._session_factory = None

    @classmethod
    def reset(cls) -> None:
        """Reset singleton instance (useful for testing).

        Warning: This should only be called during testing or shutdown.
        """
        with cls._lock:
            if cls._instance is not None:
                cls._instance.close()
            cls._instance = None
            cls._initialized = False
            logger.debug("DBConnectionManager reset")

    def __repr__(self) -> str:
        return (
            f"DBConnectionManager("
            f"env={self.config.env}, "
            f"url={self.config.db_url[:30]}..., "
            f"initialized={self._initialized})"
        )
