"""Security utilities for FluxRules API server."""

import logging
import os
import re
import secrets

logger = logging.getLogger("fluxrules.api.security")

_INSECURE_SECRET_PATTERNS: set[str] = {
    "your-secret-key-change-in-production",
    "changeme",
    "secret",
    "your-secret-key",
    "change-me",
    "default-secret",
    "test-secret",
}

_MIN_SECRET_KEY_LENGTH: int = 32


def generate_secure_secret(length: int = 64) -> str:
    return secrets.token_urlsafe(length)


def is_secret_key_insecure(key: str) -> bool:
    normalised = key.strip().lower()
    if normalised in _INSECURE_SECRET_PATTERNS:
        return True
    if len(key) < _MIN_SECRET_KEY_LENGTH:
        return True
    return False


def validate_and_resolve_secret_key(configured_key: str) -> str:
    env = os.getenv("FLUXRULES_ENV", "development").lower()
    if not is_secret_key_insecure(configured_key):
        return configured_key
    if env == "production":
        raise RuntimeError(
            "FATAL: SECRET_KEY is insecure or uses a known default. "
            "Set a strong SECRET_KEY (>=32 characters) via the SECRET_KEY "
            "environment variable before starting in production."
        )
    ephemeral = generate_secure_secret()
    logger.warning(
        "SECRET_KEY is insecure or uses a known default. "
        "An ephemeral key has been generated for this session. "
        "Tokens will NOT survive restarts."
    )
    return ephemeral


_MIN_PASSWORD_LENGTH: int = 8
_MAX_PASSWORD_LENGTH: int = 128


def validate_password_strength(password: str) -> tuple[bool, str]:
    if len(password) < _MIN_PASSWORD_LENGTH:
        return (
            False,
            f"Password must be at least {_MIN_PASSWORD_LENGTH} characters long.",
        )
    if len(password) > _MAX_PASSWORD_LENGTH:
        return False, f"Password must not exceed {_MAX_PASSWORD_LENGTH} characters."
    if not re.search(r"[A-Z]", password):
        return False, "Password must contain at least one uppercase letter."
    if not re.search(r"[a-z]", password):
        return False, "Password must contain at least one lowercase letter."
    if not re.search(r"\d", password):
        return False, "Password must contain at least one digit."
    return True, "Password meets requirements."


def parse_cors_origins(raw: str) -> list[str]:
    raw = raw.strip()
    if not raw:
        return []
    if raw == "*":
        return ["*"]
    return [origin.strip() for origin in raw.split(",") if origin.strip()]
