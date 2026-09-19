"""Application-wide configuration loaded from environment / ``.env`` file.

Security-sensitive defaults are validated at import time so that insecure
placeholders are never silently used in production.
"""

import logging

from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger("fluxrules.api.config")


class Settings(BaseSettings):
    """Central settings container - all values can be overridden via env vars."""

    PROJECT_NAME: str = "FluxRules"
    VERSION: str = "0.0.1"
    API_V1_STR: str = "/api/v1"

    DATABASE_URL: str = "sqlite:///./rule_engine.db"

    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6379
    REDIS_DB: int = 0
    SESSION_STORAGE_BACKEND: str = "auto"
    SESSION_STORAGE_PREFIX: str = "session_ctx"

    # JWT / Auth
    SECRET_KEY: str = "your-secret-key-change-in-production"  # noqa: S105 - placeholder default; must be overridden via env in production
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30

    WORKER_CONCURRENCY: int = 4
    SESSION_MAX_FACTS: int = 1000
    SESSION_TTL_SECONDS: int = 3600
    SESSION_MAX_MEMORY_MB: int = 256
    SESSION_MAX_CONCURRENT: int = 100

    # Engine settings
    USE_OPTIMIZED_ENGINE: bool = True
    RULE_ENGINE_TYPE: str = "PHREAK"  # PHREAK: lazy, scalable evaluation (the FluxRules engine)
    RULE_CACHE_TTL: int = 300
    RULE_LOCAL_CACHE_TTL: int = 60

    RULE_VALIDATION_MODE: str = "brms"

    # Evaluation hardening flags
    STRICT_TYPE_COMPARISON: bool = False
    BOOLEAN_STRING_COERCION: bool = False
    STRICT_NULL_HANDLING: bool = False
    VALIDATION_STRICT_BOOL_NUMERIC: bool = False

    # Frontend serving (optional)
    SERVE_FRONTEND: bool = False

    # CORS
    CORS_ALLOWED_ORIGINS: str = "*"
    CORS_ALLOWED_METHODS: str = "GET,POST,PUT,PATCH,DELETE,OPTIONS"
    CORS_ALLOWED_HEADERS: str = "Authorization,Content-Type,Accept"
    CORS_ALLOW_CREDENTIALS: bool = True

    # Admin seed control
    SEED_ADMIN_USER: bool = True
    ADMIN_DEFAULT_PASSWORD: str = ""
    ADMIN_FORCE_PASSWORD_CHANGE: bool = True

    # Database reliability
    DB_FALLBACK_ENABLED: bool = True

    # Schema versioning
    SCHEMA_VERSION: str = "003"

    # Audit / retention
    AUDIT_RETENTION_DAYS: int = 0
    AUDIT_INTEGRITY_ENABLED: bool = True

    # Scheduled audit policy
    AUDIT_SCHEDULER_ENABLED: bool = False

    # Environment flag
    FLUXRULES_ENV: str = "development"

    # Tuple Memory Management (TTL + Quotas)
    TUPLE_TTL_SECONDS: int = 300  # 5 minutes
    TUPLE_CLEANUP_INTERVAL_SECONDS: int = 60
    RULE_MEMORY_QUOTA_MB: float = 100.0
    RULE_QUOTA_ENFORCEMENT: str = "warn"  # "warn", "reject", or "evict"

    model_config = SettingsConfigDict(case_sensitive=True, env_file=".env")


settings = Settings()


def _resolve_session_storage_backend(configured_backend: str, env: str) -> str:
    backend = configured_backend.strip().lower()
    if backend in {"memory", "redis"}:
        return backend
    if backend == "auto":
        return "redis" if env.strip().lower() == "production" else "memory"
    raise ValueError("SESSION_STORAGE_BACKEND must be one of: auto, memory, redis")


settings.SESSION_STORAGE_BACKEND = _resolve_session_storage_backend(
    settings.SESSION_STORAGE_BACKEND,
    settings.FLUXRULES_ENV,
)

# Resolve and validate the JWT secret key.
#
# This is deliberately *lazy*. Importing `fluxrules.api.config` happens as a
# side effect of the persistence layer, so validating at import time emitted a
# security warning during plain library use, with no server and no auth
# involved. Security warnings for unused subsystems train users to ignore
# warnings, so the check is deferred until the key is actually read.
from fluxrules.api.security import validate_and_resolve_secret_key  # noqa: E402

_resolved_secret_key: str | None = None


def get_secret_key() -> str:
    """Return the validated JWT secret key, resolving it on first use.

    Raises:
        RuntimeError: If the key is insecure and ``FLUXRULES_ENV=production``.
    """
    global _resolved_secret_key
    if _resolved_secret_key is None:
        _resolved_secret_key = validate_and_resolve_secret_key(settings.SECRET_KEY)
        settings.SECRET_KEY = _resolved_secret_key
    return _resolved_secret_key
