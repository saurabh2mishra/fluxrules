"""Logging configuration and utilities for FluxRules.

Provides structured logging with optional request-ID tracking,
suitable for production monitoring and debugging.
"""

from __future__ import annotations

import logging
import sys

_CONFIGURED = False


class RequestIDFilter(logging.Filter):
    """Inject a ``request_id`` attribute into every log record."""

    def __init__(self, request_id: str | None = None) -> None:
        super().__init__()
        self.request_id = request_id or ""

    def filter(self, record: logging.LogRecord) -> bool:
        """Add request_id to the log record."""
        record.request_id = self.request_id  # type: ignore[attr-defined]
        return True


def get_logger(name: str) -> logging.Logger:
    """Return a logger for *name*, configuring defaults on first call.

    Args:
        name: Typically ``__name__`` of the calling module.

    Returns:
        A configured ``logging.Logger`` instance.
    """
    configure_logging()
    return logging.getLogger(name)


def configure_logging(
    level: str = "INFO",
    fmt: str = "text",
) -> None:
    """Configure application-wide logging (idempotent).

    Args:
        level: Logging level (``DEBUG``, ``INFO``, ``WARNING``, ``ERROR``).
        fmt: ``"text"`` for human-readable, ``"json"`` for structured output.
    """
    global _CONFIGURED
    if _CONFIGURED:
        return
    _CONFIGURED = True

    if fmt == "json":
        log_format = (
            '{"time":"%(asctime)s","level":"%(levelname)s",'
            '"logger":"%(name)s","message":"%(message)s"}'
        )
    else:
        log_format = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"

    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(logging.Formatter(log_format))

    root = logging.getLogger("fluxrules")
    root.setLevel(getattr(logging, level.upper(), logging.INFO))
    if not root.handlers:
        root.addHandler(handler)
