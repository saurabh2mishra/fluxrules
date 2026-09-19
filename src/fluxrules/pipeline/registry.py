"""Transform registry for discovery and (de)serialization.

A :class:`TransformRegistry` maps transform type names to classes so pipelines
serialized via :meth:`FactPipeline.to_dict` can be reconstructed with
:meth:`FactPipeline.from_dict`. Stock transforms are auto-registered in the
process-wide default registry.
"""

from __future__ import annotations

from typing import Any

from fluxrules.pipeline.base import Transform

__all__ = [
    "TransformRegistry",
    "default_registry",
    "register",
]


class TransformRegistry:
    """Register transform classes by name and rebuild them from dicts."""

    def __init__(self) -> None:
        self._registry: dict[str, type[Transform]] = {}

    def register(self, transform_cls: type[Transform], name: str | None = None) -> None:
        """Register ``transform_cls`` under ``name`` (defaults to class name).

        Raises:
            ValueError: If the name is already registered to a different class.
        """
        key = name or transform_cls.__name__
        existing = self._registry.get(key)
        if existing is not None and existing is not transform_cls:
            raise ValueError(f"Transform name '{key}' already registered to {existing.__name__}")
        self._registry[key] = transform_cls

    def get(self, name: str) -> type[Transform]:
        """Look up a registered transform class by name."""
        if name not in self._registry:
            raise KeyError(f"No transform registered under '{name}'")
        return self._registry[name]

    def names(self) -> list[str]:
        """Return the sorted list of registered transform names."""
        return sorted(self._registry)

    def deserialize(self, spec: dict[str, Any]) -> Transform:
        """Rebuild a transform from a :meth:`Transform.to_dict` payload."""
        type_name = spec.get("type")
        if not type_name:
            raise ValueError("Transform spec missing 'type' key")
        transform_cls = self.get(type_name)
        return transform_cls.from_dict(spec)

    def __contains__(self, name: str) -> bool:
        return name in self._registry

    def __len__(self) -> int:
        return len(self._registry)


_DEFAULT_REGISTRY: TransformRegistry | None = None


def default_registry() -> TransformRegistry:
    """Return the process-wide registry, auto-registering stock transforms."""
    global _DEFAULT_REGISTRY
    if _DEFAULT_REGISTRY is None:
        registry = TransformRegistry()
        from fluxrules.pipeline.transforms.builtin import (
            Defaults,
            FieldType,
            Flatten,
            Rename,
            Require,
        )

        for transform_cls in (Flatten, Rename, FieldType, Defaults, Require):
            registry.register(transform_cls)
        _DEFAULT_REGISTRY = registry
    return _DEFAULT_REGISTRY


def register(transform_cls: type[Transform], name: str | None = None) -> type[Transform]:
    """Register ``transform_cls`` in the default registry (usable as a decorator).

    Example:
        >>> @register
        ... class MyTransform(Transform):
        ...     ...
    """
    default_registry().register(transform_cls, name)
    return transform_cls
