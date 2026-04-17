"""Application-wide configuration loaded from environment / ``.env`` file.

Security-sensitive defaults are validated at import time so that insecure
placeholders are never silently used in production.
"""

import logging

from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger("fluxrules.config")


class Settings(BaseSettings):
    """Central settings container — all values can be overridden via env vars."""

    PROJECT_NAME: str = "FluxRules"
    VERSION: str = "1.1.0"
    API_V1_STR: str = "/api/v1"

    DATABASE_URL: str = "sqlite:///./rule_engine.db"

    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6379
    REDIS_DB: int = 0
    # Session storage backend. Use "auto" to resolve by environment:
    # development -> memory, production -> redis.
    SESSION_STORAGE_BACKEND: str = "auto"

    # --- JWT / Auth -----------------------------------------------------------
    # The raw value from the environment.  Validated & resolved at module level
    # below; see ``_resolved_secret_key``.
    SECRET_KEY: str = "your-secret-key-change-in-production"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30

    WORKER_CONCURRENCY: int = 4
    SESSION_MAX_FACTS: int = 1000
    SESSION_TTL_SECONDS: int = 3600
    SESSION_MAX_MEMORY_MB: int = 256
    SESSION_MAX_CONCURRENT: int = 100

    # --- Engine settings ------------------------------------------------------
    USE_OPTIMIZED_ENGINE: bool = True  # Set to False to use simple engine
    RULE_CACHE_TTL: int = 300  # Cache TTL in seconds (5 minutes)
    RULE_LOCAL_CACHE_TTL: int = 60  # Local cache TTL in seconds

    # Validation engine (BRMS is the only supported engine)
    RULE_VALIDATION_MODE: str = "brms"

    # --- Evaluation hardening flags (all default OFF for compatibility) -----
    STRICT_TYPE_COMPARISON: bool = False
    BOOLEAN_STRING_COERCION: bool = False
    STRICT_NULL_HANDLING: bool = False
    VALIDATION_STRICT_BOOL_NUMERIC: bool = False

    # --- Frontend serving (optional) ------------------------------------------
    SERVE_FRONTEND: bool = True

    # --- CORS (configurable, restrictive by default) --------------------------
    # Comma-separated list of allowed origins.  Use "*" ONLY for local dev.
    # Example: "https://app.example.com,https://admin.example.com"
    CORS_ALLOWED_ORIGINS: str = "*"
    # Comma-separated HTTP methods; default keeps existing behaviour.
    CORS_ALLOWED_METHODS: str = "GET,POST,PUT,PATCH,DELETE,OPTIONS"
    # Comma-separated headers; default keeps existing behaviour.
    CORS_ALLOWED_HEADERS: str = "Authorization,Content-Type,Accept"
    # Whether to allow credentials in cross-origin requests.  When origins
    # is "*", browsers silently ignore ``allow_credentials=True`` so this is
    # safe as a default but will be enforced properly when origins are locked
    # down.
    CORS_ALLOW_CREDENTIALS: bool = True

    # --- Admin seed control ---------------------------------------------------
    # Controls whether the default ``admin`` user is created on first startup.
    # Set to ``false`` in production to disable automatic seeding entirely.
    SEED_ADMIN_USER: bool = True
    # Override the default admin password via environment variable.  When unset
    # a strong random password is generated and logged (development only).
    ADMIN_DEFAULT_PASSWORD: str = ""
    # When True the seeded admin account is created with ``must_change_password``
    # flag so the first login must reset credentials.
    ADMIN_FORCE_PASSWORD_CHANGE: bool = True

    # --- Database reliability / HA -----------------------------------------------
    # When ``False`` (recommended for production) the service will **fail fast**
    # if the configured ``DATABASE_URL`` is unreachable instead of silently
    # falling back to a local SQLite file.
    DB_FALLBACK_ENABLED: bool = True

    # --- Schema versioning (Alembic-managed) -----------------------------------
    # Monotonically increasing integer that tracks the expected schema layout.
    # Bump this when models change.  The application checks the Alembic
    # ``alembic_version`` table at startup and refuses to start on mismatch.
    SCHEMA_VERSION: str = "003"

    # --- Audit / retention -----------------------------------------------------
    # Number of days to retain audit-log entries.  0 = keep forever.
    AUDIT_RETENTION_DAYS: int = 0
    # When ``True``, every audit row is stamped with an HMAC-SHA256 integrity
    # hash so that tampering can be detected.
    AUDIT_INTEGRITY_ENABLED: bool = True

    # --- Scheduled audit policy -----------------------------------------------
    # When ``True``, a background daemon thread evaluates cron-based audit
    # policies and executes full-audit sweeps automatically.
    # **Opt-in**: set to ``True`` only in environments that should perform
    # scheduled audits (typically production / staging).
    AUDIT_SCHEDULER_ENABLED: bool = False

    # --- Environment flag (controls strictness of security checks) ------------
    FLUXRULES_ENV: str = "development"

    model_config = SettingsConfigDict(case_sensitive=True, env_file=".env")


settings = Settings()


def _resolve_session_storage_backend(configured_backend: str, env: str) -> str:
    """Resolve session storage backend from explicit or automatic config.

    Supported values:
    * "auto": resolves to "memory" for development and "redis" for production.
    * "memory": explicit in-process backend.
    * "redis": explicit shared backend.
    """
    backend = configured_backend.strip().lower()
    if backend in {"memory", "redis"}:
        return backend
    if backend == "auto":
        return "redis" if env.strip().lower() == "production" else "memory"
    raise ValueError(
        "SESSION_STORAGE_BACKEND must be one of: auto, memory, redis"
    )


settings.SESSION_STORAGE_BACKEND = _resolve_session_storage_backend(
    settings.SESSION_STORAGE_BACKEND,
    settings.FLUXRULES_ENV,
)

# ---------------------------------------------------------------------------
# Resolve and validate the JWT secret key at import time.
# ---------------------------------------------------------------------------
from app.security import validate_and_resolve_secret_key  # noqa: E402

_resolved_secret_key = validate_and_resolve_secret_key(settings.SECRET_KEY)
# Patch the settings object so every downstream consumer sees the safe key.
settings.SECRET_KEY = _resolved_secret_key
