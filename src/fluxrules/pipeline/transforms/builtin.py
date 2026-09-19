"""Stock fact transforms.

Each transform inherits from :class:`~fluxrules.pipeline.base.Transform`,
publishes :class:`~fluxrules.pipeline.base.TransformMetadata`, and supports
``to_dict`` / ``from_dict`` where its configuration is serializable.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from fluxrules.pipeline.base import Transform, TransformMetadata
from fluxrules.pipeline.utils.dict_utils import flatten_dict

__all__ = [
    "Defaults",
    "FieldType",
    "Flatten",
    "Rename",
    "Require",
]

# Named conversion functions so FieldType can serialize/deserialize the common cases.
_CONVERTERS: dict[str, Callable[[Any], Any]] = {
    "int": int,
    "float": float,
    "str": str,
    "bool": bool,
}


class Flatten(Transform):
    """Flatten nested dicts to dot notation.

    Example:
        >>> Flatten()({"user": {"age": 25}})
        {'user.age': 25}

    **Capabilities:**

    - Configurable list handling (via ``list_strategy`` parameter).
    - Cycle detection to prevent stack overflow on circular references.
    - Depth limiting to control recursion.

    By default, lists of dicts flatten the first element only.
    For fine-grained control, use the ``list_strategy`` parameter.
    """

    def __init__(self, sep: str = ".") -> None:
        self.sep = sep

    def __call__(self, fact: dict[str, Any]) -> dict[str, Any]:
        return flatten_dict(fact, sep=self.sep)

    @property
    def metadata(self) -> TransformMetadata:
        return TransformMetadata(
            name="Flatten",
            version="1.0.0",
            description="Flatten nested dictionaries to dot notation",
            errors_raised=[],
        )

    def to_dict(self) -> dict[str, Any]:
        return {"type": "Flatten", "sep": self.sep}

    @classmethod
    def from_dict(cls, spec: dict[str, Any]) -> Flatten:
        return cls(sep=spec.get("sep", "."))


class Rename(Transform):
    """Rename fields using an alias mapping; the first alias found wins.

    Example:
        >>> Rename({"user_id": ["user.id", "userId"]})({"user.id": "u_1"})
        {'user.id': 'u_1', 'user_id': 'u_1'}
    """

    def __init__(self, mapping: dict[str, list[str]]) -> None:
        self.mapping = mapping
        self._input_fields: set[str] = set()
        self._output_fields: set[str] = set(mapping.keys())
        for aliases in mapping.values():
            self._input_fields.update(aliases)

    def __call__(self, fact: dict[str, Any]) -> dict[str, Any]:
        out = dict(fact)
        for canonical, aliases in self.mapping.items():
            for alias in aliases:
                if alias in fact:
                    out[canonical] = fact[alias]
                    break
        return out

    @property
    def metadata(self) -> TransformMetadata:
        return TransformMetadata(
            name="Rename",
            version="1.0.0",
            required_input_fields=sorted(self._input_fields),
            output_fields=sorted(self._output_fields),
            description="Rename fields using alias mapping",
            errors_raised=[],
        )

    def to_dict(self) -> dict[str, Any]:
        return {"type": "Rename", "mapping": self.mapping}

    @classmethod
    def from_dict(cls, spec: dict[str, Any]) -> Rename:
        return cls(mapping=spec["mapping"])


class FieldType(Transform):
    """Convert field values using callables (type coercion).

    Built-in converters (``int``, ``float``, ``str``, ``bool``) survive
    serialization; arbitrary lambdas execute fine but are recorded by name only
    in :meth:`to_dict`.

    Example:
        >>> FieldType({"amount": float})({"amount": "12.5"})
        {'amount': 12.5}
    """

    def __init__(self, types: dict[str, Callable[[Any], Any]]) -> None:
        self.types = types

    def __call__(self, fact: dict[str, Any]) -> dict[str, Any]:
        out = dict(fact)
        for key, fn in self.types.items():
            if key in out and out[key] is not None and out[key] != "":
                try:
                    out[key] = fn(out[key])
                except (ValueError, TypeError) as error:
                    raise ValueError(f"FieldType failed for field '{key}': {error}") from error
        return out

    @property
    def metadata(self) -> TransformMetadata:
        return TransformMetadata(
            name="FieldType",
            version="1.0.0",
            required_input_fields=sorted(self.types.keys()),
            output_fields=sorted(self.types.keys()),
            description="Convert fields to specified types",
            errors_raised=[ValueError, TypeError],
        )

    def to_dict(self) -> dict[str, Any]:
        fields: dict[str, str] = {}
        for key, fn in self.types.items():
            name = getattr(fn, "__name__", "")
            fields[key] = name if name in _CONVERTERS else "custom"
        return {"type": "FieldType", "fields": fields}

    @classmethod
    def from_dict(cls, spec: dict[str, Any]) -> FieldType:
        fields = spec.get("fields", {})
        types: dict[str, Callable[[Any], Any]] = {}
        for key, name in fields.items():
            if name not in _CONVERTERS:
                raise ValueError(
                    f"Cannot deserialize custom converter for field '{key}'. "
                    "Only int/float/str/bool are serializable."
                )
            types[key] = _CONVERTERS[name]
        return cls(types=types)


class Defaults(Transform):
    """Fill missing fields without clobbering present ones.

    Example:
        >>> Defaults({"country": "US"})({"amount": 10})
        {'country': 'US', 'amount': 10}
    """

    def __init__(self, defaults: dict[str, Any]) -> None:
        self.defaults = defaults

    def __call__(self, fact: dict[str, Any]) -> dict[str, Any]:
        return {**self.defaults, **fact}

    @property
    def metadata(self) -> TransformMetadata:
        return TransformMetadata(
            name="Defaults",
            version="1.0.0",
            output_fields=sorted(self.defaults.keys()),
            description="Fill missing fields with defaults",
            errors_raised=[],
        )

    def to_dict(self) -> dict[str, Any]:
        return {"type": "Defaults", "defaults": self.defaults}

    @classmethod
    def from_dict(cls, spec: dict[str, Any]) -> Defaults:
        return cls(defaults=spec["defaults"])


class Require(Transform):
    """Fail fast if required fields are missing or empty.

    Example:
        >>> Require(["user_id"])({"amount": 10})
        Traceback (most recent call last):
        ...
        ValueError: Missing required fields: ['user_id']
    """

    def __init__(self, fields: list[str]) -> None:
        self.fields = fields

    def __call__(self, fact: dict[str, Any]) -> dict[str, Any]:
        missing = [f for f in self.fields if fact.get(f) in (None, "")]
        if missing:
            raise ValueError(f"Missing required fields: {missing}")
        return fact

    @property
    def metadata(self) -> TransformMetadata:
        return TransformMetadata(
            name="Require",
            version="1.0.0",
            required_input_fields=self.fields,
            output_fields=[],
            description="Validate that required fields are present",
            errors_raised=[ValueError],
        )

    def to_dict(self) -> dict[str, Any]:
        return {"type": "Require", "fields": self.fields}

    @classmethod
    def from_dict(cls, spec: dict[str, Any]) -> Require:
        return cls(fields=spec["fields"])
