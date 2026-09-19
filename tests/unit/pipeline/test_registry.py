"""Tests for the TransformRegistry and pipeline (de)serialization."""

from __future__ import annotations

from typing import Any

import pytest

from fluxrules.pipeline.base import Transform, TransformMetadata
from fluxrules.pipeline.core import FactPipeline
from fluxrules.pipeline.registry import (
    TransformRegistry,
    default_registry,
    register,
)
from fluxrules.pipeline.transforms.builtin import Defaults, Flatten, Rename, Require


class TestTransformRegistry:
    def test_register_and_get(self):
        registry = TransformRegistry()
        registry.register(Flatten)
        assert registry.get("Flatten") is Flatten

    def test_register_custom_name(self):
        registry = TransformRegistry()
        registry.register(Flatten, name="MyFlatten")
        assert registry.get("MyFlatten") is Flatten

    def test_get_missing_raises(self):
        registry = TransformRegistry()
        with pytest.raises(KeyError):
            registry.get("Nope")

    def test_duplicate_same_class_ok(self):
        registry = TransformRegistry()
        registry.register(Flatten)
        registry.register(Flatten)  # idempotent

    def test_duplicate_different_class_raises(self):
        registry = TransformRegistry()
        registry.register(Flatten, name="X")
        with pytest.raises(ValueError, match="already registered"):
            registry.register(Rename, name="X")

    def test_names_sorted(self):
        registry = TransformRegistry()
        registry.register(Rename)
        registry.register(Flatten)
        assert registry.names() == ["Flatten", "Rename"]

    def test_contains_and_len(self):
        registry = TransformRegistry()
        registry.register(Flatten)
        assert "Flatten" in registry
        assert len(registry) == 1

    def test_deserialize_missing_type_raises(self):
        registry = TransformRegistry()
        with pytest.raises(ValueError, match="missing 'type'"):
            registry.deserialize({})


class TestDefaultRegistry:
    def test_stock_transforms_registered(self):
        registry = default_registry()
        for name in ("Flatten", "Rename", "FieldType", "Defaults", "Require"):
            assert name in registry

    def test_singleton(self):
        assert default_registry() is default_registry()

    def test_register_decorator(self):
        @register
        class CustomTransform(Transform):
            def __call__(self, fact: dict[str, Any]) -> dict[str, Any]:
                return fact

            @property
            def metadata(self) -> TransformMetadata:
                return TransformMetadata(name="CustomTransform")

        assert "CustomTransform" in default_registry()


class TestPipelineSerializationRoundTrip:
    def test_simple_round_trip(self):
        original = FactPipeline([Flatten(), Defaults({"a": 1})])
        rebuilt = FactPipeline.from_dict(original.to_dict())
        assert rebuilt({"x": {"y": 1}}) == original({"x": {"y": 1}})

    def test_full_round_trip(self):
        original = FactPipeline(
            [
                Flatten(),
                Rename({"user_id": ["user.id"]}),
                Defaults({"country": "US"}),
                Require(["user_id"]),
            ]
        )
        rebuilt = FactPipeline.from_dict(original.to_dict())
        fact = {"user": {"id": "u_1"}}
        assert rebuilt(dict(fact)) == original(dict(fact))

    def test_explicit_registry(self):
        registry = TransformRegistry()
        registry.register(Defaults)
        original = FactPipeline([Defaults({"a": 1})])
        rebuilt = FactPipeline.from_dict(original.to_dict(), registry=registry)
        assert rebuilt({}) == {"a": 1}
