"""Base classes for fact transforms.

Every transform must:

1. Inherit from :class:`Transform`.
2. Implement ``__call__(fact) -> dict``.
3. Implement the ``metadata`` property.
4. Document the errors it raises (via :class:`TransformMetadata`).

The ABC gives us static type checking, introspection, and serialization,
replacing the prototype's bare ``Transform = Callable[[dict], dict]`` alias.
"""

from __future__ import annotations

import hashlib
import json
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Callable

    from fluxrules.pipeline.core import FactPipeline

__all__ = [
    "Transform",
    "TransformMetadata",
]


@dataclass
class TransformMetadata:
    """Published contract of a transform.

    Metadata makes a pipeline *inspectable*: callers can discover the fields a
    transform needs, the fields it produces, and the exceptions it may raise,
    all without executing it.
    """

    name: str
    """Human-readable name (e.g. ``"Rename"``, ``"Coerce"``)."""

    version: str = "1.0.0"
    """Transform version (for auditing and breaking-change detection)."""

    required_input_fields: list[str] = field(default_factory=list)
    """Fields the transform needs to be present to do useful work."""

    output_fields: list[str] = field(default_factory=list)
    """Fields the transform guarantees (or is likely) to output."""

    errors_raised: list[type[Exception]] = field(default_factory=list)
    """Exception types this transform may raise."""

    description: str = ""
    """Human-readable description of what the transform does."""

    @property
    def signature(self) -> str:
        """Deterministic 8-char signature for change detection.

        Two metadata objects with the same name, version, and field sets
        produce the same signature, making it easy to detect when a
        transform's contract has changed.
        """
        content = json.dumps(
            {
                "name": self.name,
                "version": self.version,
                "required_input_fields": sorted(self.required_input_fields),
                "output_fields": sorted(self.output_fields),
            },
            sort_keys=True,
        )
        return hashlib.sha256(content.encode()).hexdigest()[:8]


class Transform(ABC):
    """Base class for all fact transforms.

    A transform is a pure function ``dict[str, Any] -> dict[str, Any]`` that
    can validate, enrich, clean, extract, or flatten facts. Failures are
    raised as exceptions and routed by the loader's error policy.

    Example:
        >>> class Uppercase(Transform):
        ...     def __init__(self, fields: list[str]) -> None:
        ...         self.fields = fields
        ...
        ...     def __call__(self, fact: dict[str, Any]) -> dict[str, Any]:
        ...         out = dict(fact)
        ...         for f in self.fields:
        ...             if isinstance(out.get(f), str):
        ...                 out[f] = out[f].upper()
        ...         return out
        ...
        ...     @property
        ...     def metadata(self) -> TransformMetadata:
        ...         return TransformMetadata(
        ...             name="Uppercase",
        ...             required_input_fields=self.fields,
        ...             output_fields=self.fields,
        ...         )
    """

    @abstractmethod
    def __call__(self, fact: dict[str, Any]) -> dict[str, Any]:
        """Apply the transform to a single fact and return the result."""
        ...

    @property
    @abstractmethod
    def metadata(self) -> TransformMetadata:
        """Introspection: what this transform requires, outputs, and raises."""
        ...

    # ------------------------------------------------------------------
    # Composition operators
    # ------------------------------------------------------------------
    #
    # A bare transform composes just like a pipeline: ``a >> b`` and ``a | b``
    # both "just work" by promoting ``self`` into a one-step
    # :class:`~fluxrules.pipeline.core.FactPipeline` and delegating. This keeps
    # the ergonomic, prototype-style syntax while still producing a fully
    # featured pipeline (inspectable, serializable, observable).

    def _as_pipeline(self) -> FactPipeline:
        """Wrap this transform in a single-step :class:`FactPipeline`."""
        from fluxrules.pipeline.core import FactPipeline

        return FactPipeline([self], name=type(self).__name__)

    def __rshift__(self, other: FactPipeline | Transform) -> FactPipeline:
        """``a >> b``: run ``a``, then feed its output into ``b``.

        Lets transforms be chained directly (``Flatten() >> Require([...])``)
        without manually wrapping each one in a :class:`FactPipeline`.
        """
        return self._as_pipeline() >> other

    def __or__(self, other: FactPipeline | Transform) -> FactPipeline:
        """``a | b``: try ``a``; if it raises, run ``b`` on the original fact."""
        return self._as_pipeline() | other

    def when(
        self,
        predicate: Callable[[dict[str, Any]], bool],
        then: FactPipeline | Transform,
        otherwise: FactPipeline | Transform | None = None,
    ) -> FactPipeline:
        """Branch on ``predicate`` after this transform.

        Equivalent to ``FactPipeline([self]).when(...)``: run ``then`` when
        ``predicate`` is true, otherwise run ``otherwise`` (or pass through).
        """
        return self._as_pipeline().when(predicate, then, otherwise)

    def to_dict(self) -> dict[str, Any]:
        """Serialize this transform to a plain dict (for YAML/JSON).

        The default implementation emits only the type and version. Transforms
        with configuration should override this to include their settings so
        they can be reconstructed via :meth:`from_dict`.
        """
        return {
            "type": type(self).__name__,
            "version": self.metadata.version,
        }

    @classmethod
    def from_dict(cls, spec: dict[str, Any]) -> Transform:
        """Reconstruct a transform from a :meth:`to_dict` payload.

        The default raises :class:`NotImplementedError`; transforms that
        support serialization override this.
        """
        raise NotImplementedError(f"{cls.__name__} does not support from_dict")
