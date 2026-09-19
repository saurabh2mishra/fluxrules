"""Structural validation for fact dicts.

This module guarantees the engine's *minimum* contract for a fact, with zero
external dependencies:

1. the fact is a ``dict``;
2. every key is a ``str``;
3. no value is a nested ``dict`` or ``list`` (the flat contract).

``None`` values are allowed (missing data is fine), and empty dicts are allowed
(a transform may legitimately drop every field).

The richer, schema-aware, *type-checking* layer lives in
:mod:`fluxrules.pipeline.schema` (Pydantic, optional) and builds on top of the
checks here. Keeping this layer dependency-free means it can run on the engine
hot path and inside every pipeline without pulling in Pydantic.
"""

from __future__ import annotations

from typing import Any

__all__ = [
    "FactValidator",
    "InvalidFactError",
]


class InvalidFactError(ValueError):
    """Raised when a fact violates the structural contract.

    Subclasses :class:`ValueError` so the existing pipeline
    :class:`~fluxrules.pipeline.error_policy.ErrorPolicy` (and the
    :class:`~fluxrules.pipeline.loaders.FactLoader` ``on_error`` handling) can
    route it like any other transform failure - no special-casing required.

    Attributes:
        source: Where the bad fact came from (a transform name, ``"engine"``,
            etc.) - used to point developers at the real culprit.
        reason: Short, human-readable description of the violation.
        detail: Optional extra context (offending types, field names, ...).
    """

    def __init__(self, source: str, reason: str, detail: str = "") -> None:
        self.source = source
        self.reason = reason
        self.detail = detail
        message = f"{source!r} produced an invalid fact: {reason}"
        if detail:
            message += f" ({detail})"
        super().__init__(message)


class FactValidator:
    """Static, schema-agnostic structural checks for facts.

    Usage:
        >>> FactValidator.validate("MyTransform", {"x": 1, "y": None})
        {'x': 1, 'y': None}
        >>> FactValidator.validate("MyTransform", None)
        Traceback (most recent call last):
            ...
        fluxrules.pipeline.validators.InvalidFactError: 'MyTransform' produced
        an invalid fact: result must be a dict (got NoneType)
    """

    @staticmethod
    def validate(source: str, fact: Any) -> dict[str, Any]:
        """Validate ``fact`` and return it unchanged when valid.

        Args:
            source: Name used in error messages (e.g. the transform name).
            fact: The value to validate.

        Returns:
            ``fact`` (the same object) if it satisfies the structural contract.

        Raises:
            InvalidFactError: If ``fact`` is not a dict, has non-string keys, or
                contains nested ``dict`` / ``list`` values.
        """
        # Check 1: must be a dict.
        if not isinstance(fact, dict):
            raise InvalidFactError(
                source,
                "result must be a dict",
                f"got {type(fact).__name__}",
            )

        # Check 2: all keys must be strings.
        non_string_key_types = sorted(
            {type(key).__name__ for key in fact if not isinstance(key, str)}
        )
        if non_string_key_types:
            raise InvalidFactError(
                source,
                "all keys must be strings",
                f"found key types {non_string_key_types}",
            )

        # Check 3: no nested structures (flat contract).
        nested = {
            key: type(value).__name__
            for key, value in fact.items()
            if isinstance(value, (dict, list))
        }
        if nested:
            raise InvalidFactError(
                source,
                "facts must be flat (no nested dict/list values)",
                f"nested fields: {nested}",
            )

        return fact

    @staticmethod
    def is_valid(fact: Any) -> bool:
        """Return ``True`` if ``fact`` satisfies the structural contract.

        A non-raising convenience wrapper around :meth:`validate` for callers
        that want a boolean check (e.g. filtering a stream) instead of an
        exception.
        """
        try:
            FactValidator.validate("is_valid", fact)
        except InvalidFactError:
            return False
        return True
