"""Pydantic fact validation boundary.

This module is intentionally optional: FluxRules core can run without Pydantic,
and consumers opt into schema validation when they need strict typed contracts.

Boundary model:
    raw dict -> Pydantic model -> validated/coerced data -> flat dict

The output is always a plain ``dict[str, Any]`` to preserve the engine/pipeline
public contract.
"""

from __future__ import annotations

from typing import Any

from fluxrules.pipeline.validators import FactValidator, InvalidFactError

try:
    from pydantic import BaseModel, ConfigDict, ValidationError

    _HAS_PYDANTIC = True
except ImportError:  # pragma: no cover - no-pydantic environments
    _HAS_PYDANTIC = False


__all__ = [
    "FactSchema",
    "SchemaValidationError",
    "validate_facts",
]


class SchemaValidationError(InvalidFactError):
    """Raised when a raw fact fails schema validation at the boundary."""


def _format_pydantic_errors(exc: Any) -> str:
    """Normalize pydantic ValidationError details into a compact string."""
    details: list[str] = []
    for error in exc.errors():
        location = ".".join(str(part) for part in error.get("loc", ()))
        message = error.get("msg", "invalid value")
        if location:
            details.append(f"{location}: {message}")
        else:
            details.append(str(message))
    return "; ".join(details)


if _HAS_PYDANTIC:

    class FactSchema(BaseModel):
        """Base class for typed fact contracts.

        Default behavior forbids unknown fields (``extra='forbid'``) to catch
        misspellings early. Subclasses can override ``model_config`` as needed.
        """

        model_config = ConfigDict(extra="forbid")

        def to_facts(self) -> dict[str, Any]:
            """Return validated model data as a plain, flat dict.

            Pydantic enforces field-level typing and custom validators; this
            method adds a final structural guard to preserve the flat fact
            contract expected by the engine and pipeline transforms.
            """
            data = self.model_dump()
            return FactValidator.validate(type(self).__name__, data)

else:

    class FactSchema:  # type: ignore[no-redef]
        """Fallback placeholder used when pydantic is not installed."""

        def __init__(self, *args: Any, **kwargs: Any) -> None:
            raise ImportError(
                "FactSchema requires pydantic. Install with one of: "
                '`pip install "fluxrules[api]"`, '
                '`pip install "fluxrules[all]"`, or install pydantic directly.'
            )

        def to_facts(self) -> dict[str, Any]:
            raise ImportError(
                "FactSchema requires pydantic. Install with `fluxrules[api]` or `fluxrules[all]`."
            )


def validate_facts(
    model: type[FactSchema],
    raw: dict[str, Any],
) -> dict[str, Any]:
    """Validate ``raw`` against a ``FactSchema`` subclass and return flat dict.

    Raises:
        ImportError: If pydantic is not installed.
        SchemaValidationError: If schema validation fails.
    """
    if not _HAS_PYDANTIC:  # pragma: no cover - no-pydantic environments
        raise ImportError(
            "validate_facts requires pydantic. Install with `fluxrules[api]` "
            "or `fluxrules[all]` (or install pydantic directly)."
        )

    # Structural sanity check first for clearer source-level diagnostics.
    FactValidator.validate(getattr(model, "__name__", "FactSchema"), raw)

    try:
        instance = model(**raw)
    except ValidationError as exc:
        raise SchemaValidationError(
            getattr(model, "__name__", "FactSchema"),
            "schema validation failed",
            _format_pydantic_errors(exc),
        ) from exc

    return instance.to_facts()
