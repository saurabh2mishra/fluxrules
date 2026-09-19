"""Advanced/composed transforms.

These transforms add control flow at the *transform* level (as opposed to the
pipeline-level composition operators), enabling branching, filtering, and
fan-out without writing bespoke transform classes.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from fluxrules.pipeline.base import Transform, TransformMetadata

__all__ = [
    "Conditional",
    "DropFact",
    "Filter",
    "MapValues",
    "Switch",
]


class DropFact(Exception):
    """Raised by :class:`Filter` to signal a fact should be dropped.

    The loader treats this like any skip-able error, routing it out of the
    output stream without populating the dead-letter queue.
    """


class Conditional(Transform):
    """Apply one of two transforms based on a predicate.

    Example:
        >>> legacy = Rename({"id": ["legacy_id"]})
        >>> modern = Rename({"id": ["uuid"]})
        >>> t = Conditional(lambda f: f.get("source") == "legacy", legacy, modern)
    """

    def __init__(
        self,
        predicate: Callable[[dict[str, Any]], bool],
        then_transform: Transform,
        else_transform: Transform | None = None,
    ) -> None:
        self.predicate = predicate
        self.then_transform = then_transform
        self.else_transform = else_transform

    def __call__(self, fact: dict[str, Any]) -> dict[str, Any]:
        if self.predicate(fact):
            return self.then_transform(fact)
        if self.else_transform is not None:
            return self.else_transform(fact)
        return fact

    @property
    def metadata(self) -> TransformMetadata:
        inputs = set(self.then_transform.metadata.required_input_fields)
        outputs = set(self.then_transform.metadata.output_fields)
        errors = set(self.then_transform.metadata.errors_raised)
        if self.else_transform is not None:
            inputs.update(self.else_transform.metadata.required_input_fields)
            outputs.update(self.else_transform.metadata.output_fields)
            errors.update(self.else_transform.metadata.errors_raised)
        return TransformMetadata(
            name="Conditional",
            version="1.0.0",
            required_input_fields=sorted(inputs),
            output_fields=sorted(outputs),
            description="Branch between two transforms on a predicate",
            errors_raised=sorted(errors, key=lambda e: e.__name__),
        )


class Filter(Transform):
    """Drop facts that do not satisfy a predicate.

    Facts that fail the predicate raise :class:`DropFact`, which the loader
    routes out of the output stream.

    Example:
        >>> only_adults = Filter(lambda f: f.get("age", 0) >= 18)
    """

    def __init__(
        self,
        predicate: Callable[[dict[str, Any]], bool],
        *,
        description: str = "",
    ) -> None:
        self.predicate = predicate
        self._description = description or "Filter facts by predicate"

    def __call__(self, fact: dict[str, Any]) -> dict[str, Any]:
        if not self.predicate(fact):
            raise DropFact("fact filtered out by predicate")
        return fact

    @property
    def metadata(self) -> TransformMetadata:
        return TransformMetadata(
            name="Filter",
            version="1.0.0",
            description=self._description,
            errors_raised=[DropFact],
        )


class Switch(Transform):
    """Route a fact to the first matching transform in an ordered case list.

    Each case is a ``(predicate, transform)`` pair, evaluated in order. If none
    match, ``default`` runs (or the fact passes through unchanged).

    Example:
        >>> router = Switch(
        ...     [
        ...         (lambda f: f["kind"] == "a", transform_a),
        ...         (lambda f: f["kind"] == "b", transform_b),
        ...     ],
        ...     default=fallback_transform,
        ... )
    """

    def __init__(
        self,
        cases: list[tuple[Callable[[dict[str, Any]], bool], Transform]],
        default: Transform | None = None,
    ) -> None:
        self.cases = cases
        self.default = default

    def __call__(self, fact: dict[str, Any]) -> dict[str, Any]:
        for predicate, transform in self.cases:
            if predicate(fact):
                return transform(fact)
        if self.default is not None:
            return self.default(fact)
        return fact

    @property
    def metadata(self) -> TransformMetadata:
        outputs: set[str] = set()
        errors: set[type[Exception]] = set()
        for _, transform in self.cases:
            outputs.update(transform.metadata.output_fields)
            errors.update(transform.metadata.errors_raised)
        if self.default is not None:
            outputs.update(self.default.metadata.output_fields)
            errors.update(self.default.metadata.errors_raised)
        return TransformMetadata(
            name="Switch",
            version="1.0.0",
            output_fields=sorted(outputs),
            description="Route facts to the first matching case transform",
            errors_raised=sorted(errors, key=lambda e: e.__name__),
        )


class MapValues(Transform):
    """Apply a function to every value of selected (or all) fields.

    Example:
        >>> MapValues(str.strip, fields=["name"])({"name": "  bob "})
        {'name': 'bob'}
    """

    def __init__(
        self,
        fn: Callable[[Any], Any],
        *,
        fields: list[str] | None = None,
    ) -> None:
        self.fn = fn
        self.fields = fields

    def __call__(self, fact: dict[str, Any]) -> dict[str, Any]:
        out = dict(fact)
        keys = self.fields if self.fields is not None else list(out.keys())
        for key in keys:
            if key in out:
                out[key] = self.fn(out[key])
        return out

    @property
    def metadata(self) -> TransformMetadata:
        return TransformMetadata(
            name="MapValues",
            version="1.0.0",
            required_input_fields=self.fields or [],
            output_fields=self.fields or [],
            description="Apply a function to selected field values",
            errors_raised=[],
        )
