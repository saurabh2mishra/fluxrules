"""Security utilities for FluxRules enterprise hardening.

This module centralises secret-key validation, password-policy enforcement,
and CORS origin parsing so that security-sensitive logic lives in a single,
auditable location.
"""

import logging
import os
import secrets
import re
from typing import List

logger = logging.getLogger("fluxrules.security")

# ---------------------------------------------------------------------------
# Well-known insecure defaults that MUST NOT be used in production.
# ---------------------------------------------------------------------------
_INSECURE_SECRET_PATTERNS: set[str] = {
    "your-secret-key-change-in-production",
    "changeme",
    "secret",
    "your-secret-key",
    "change-me",
    "default-secret",
    "test-secret",
}

# Minimum acceptable secret key length (OWASP recommendation for HS256)
_MIN_SECRET_KEY_LENGTH: int = 32


def generate_secure_secret(length: int = 64) -> str:
    """Generate a cryptographically-secure URL-safe secret key.

    Args:
        length: Number of random bytes (default 64 → 86-char base64 string).

    Returns:
        A URL-safe base64-encoded secret key.
    """
    return secrets.token_urlsafe(length)


def is_secret_key_insecure(key: str) -> bool:
    """Return True when *key* matches a known-insecure placeholder or is too short.

    This check is intentionally conservative – it will flag obvious defaults
    but will **not** reject a user-supplied key that simply looks weak.
    """
    normalised = key.strip().lower()
    if normalised in _INSECURE_SECRET_PATTERNS:
        return True
    if len(key) < _MIN_SECRET_KEY_LENGTH:
        return True
    return False


def validate_and_resolve_secret_key(configured_key: str) -> str:
    """Validate the configured secret key and resolve it securely.

    Behaviour:
    * **Production** (``FLUXRULES_ENV=production``): raises ``RuntimeError``
      if the key is insecure — the service must not start with weak secrets.
    * **Development / test** (default): logs a loud warning and auto-generates
      a random ephemeral key so that local ``uvicorn`` still works out of
      the box.

    Args:
        configured_key: The raw ``SECRET_KEY`` value from settings.

    Returns:
        A validated (or auto-generated) secret key string.

    Raises:
        RuntimeError: In production when the key is insecure.
    """
    env = os.getenv("FLUXRULES_ENV", "development").lower()

    if not is_secret_key_insecure(configured_key):
        return configured_key

    if env == "production":
        raise RuntimeError(
            "FATAL: SECRET_KEY is insecure or uses a known default. "
            "Set a strong SECRET_KEY (≥32 characters) via the SECRET_KEY "
            "environment variable before starting in production. "
            "Generate one with: python -c \"import secrets; print(secrets.token_urlsafe(64))\""
        )

    # Non-production: auto-generate an ephemeral key and warn loudly.
    ephemeral = generate_secure_secret()
    logger.warning(
        "⚠️  SECRET_KEY is insecure or uses a known default. "
        "An ephemeral key has been generated for this session. "
        "Tokens will NOT survive restarts. "
        "Set SECRET_KEY in your environment or .env file for persistence. "
        "Generate one with: python -c \"import secrets; print(secrets.token_urlsafe(64))\""
    )
    return ephemeral


# ---------------------------------------------------------------------------
# Password-policy enforcement (OWASP-aligned)
# ---------------------------------------------------------------------------
_MIN_PASSWORD_LENGTH: int = 8
_MAX_PASSWORD_LENGTH: int = 128


def validate_password_strength(password: str) -> tuple[bool, str]:
    """Validate that a password meets minimum enterprise requirements.

    Rules (OWASP-aligned):
    * Length between 8 and 128 characters.
    * At least one uppercase letter.
    * At least one lowercase letter.
    * At least one digit.

    Args:
        password: Plaintext password to validate.

    Returns:
        A ``(is_valid, message)`` tuple.
    """
    if len(password) < _MIN_PASSWORD_LENGTH:
        return False, f"Password must be at least {_MIN_PASSWORD_LENGTH} characters long."
    if len(password) > _MAX_PASSWORD_LENGTH:
        return False, f"Password must not exceed {_MAX_PASSWORD_LENGTH} characters."
    if not re.search(r"[A-Z]", password):
        return False, "Password must contain at least one uppercase letter."
    if not re.search(r"[a-z]", password):
        return False, "Password must contain at least one lowercase letter."
    if not re.search(r"\d", password):
        return False, "Password must contain at least one digit."
    return True, "Password meets requirements."


# ---------------------------------------------------------------------------
# CORS origin parsing
# ---------------------------------------------------------------------------

def parse_cors_origins(raw: str) -> List[str]:
    """Parse a comma-separated CORS origins string into a clean list.

    Special handling:
    * ``"*"`` → ``["*"]`` (kept for explicit opt-in during development).
    * Empty/whitespace → ``[]`` (no origins allowed).

    Args:
        raw: Comma-separated origin URLs, e.g.
             ``"https://app.example.com, https://admin.example.com"``.

    Returns:
        List of trimmed, non-empty origin strings.
    """
    raw = raw.strip()
    if not raw:
        return []
    if raw == "*":
        return ["*"]
    return [origin.strip() for origin in raw.split(",") if origin.strip()]
