"""Tests for the Transform ABC and TransformMetadata."""

from __future__ import annotations

from typing import Any

import pytest

from fluxrules.pipeline.base import Transform, TransformMetadata
from fluxrules.pipeline.core import FactPipeline


class DummyTransform(Transform):
    """Minimal concrete transform used across tests."""

    def __call__(self, fact: dict[str, Any]) -> dict[str, Any]:
        out = dict(fact)
        out["test"] = "pass"
        return out

    @property
    def metadata(self) -> TransformMetadata:
        return TransformMetadata(name="Dummy", output_fields=["test"])


class AddField(Transform):
    """Set a single field to a constant; handy for composition tests."""

    def __init__(self, key: str, value: Any) -> None:
        self.key = key
        self.value = value

    def __call__(self, fact: dict[str, Any]) -> dict[str, Any]:
        out = dict(fact)
        out[self.key] = self.value
        return out

    @property
    def metadata(self) -> TransformMetadata:
        return TransformMetadata(name=f"AddField[{self.key}]", output_fields=[self.key])


class Boom(Transform):
    """Always raises, to exercise the fallback (``|``) operator."""

    def __call__(self, fact: dict[str, Any]) -> dict[str, Any]:
        raise ValueError("boom")

    @property
    def metadata(self) -> TransformMetadata:
        return TransformMetadata(name="Boom", errors_raised=[ValueError])


class TestTransformABC:
    def test_transform_cannot_be_instantiated(self):
        with pytest.raises(TypeError):
            Transform()  # type: ignore[abstract]

    def test_concrete_transform_is_callable(self):
        result = DummyTransform()({})
        assert result["test"] == "pass"

    def test_default_to_dict_includes_type_and_version(self):
        d = DummyTransform().to_dict()
        assert d["type"] == "DummyTransform"
        assert d["version"] == "1.0.0"

    def test_default_from_dict_raises(self):
        with pytest.raises(NotImplementedError):
            DummyTransform.from_dict({})


class TestTransformMetadata:
    def test_defaults(self):
        meta = TransformMetadata(name="X")
        assert meta.version == "1.0.0"
        assert meta.required_input_fields == []
        assert meta.output_fields == []
        assert meta.errors_raised == []
        assert meta.description == ""

    def test_signature_is_deterministic(self):
        a = TransformMetadata(name="X", output_fields=["b", "a"])
        b = TransformMetadata(name="X", output_fields=["a", "b"])
        # Order-independent because the signature sorts field lists.
        assert a.signature == b.signature

    def test_signature_changes_with_name(self):
        a = TransformMetadata(name="X")
        b = TransformMetadata(name="Y")
        assert a.signature != b.signature

    def test_signature_changes_with_version(self):
        a = TransformMetadata(name="X", version="1.0.0")
        b = TransformMetadata(name="X", version="2.0.0")
        assert a.signature != b.signature

    def test_signature_length(self):
        assert len(TransformMetadata(name="X").signature) == 8


class TestTransformComposition:
    """Bare transforms compose with ``>>``, ``|`` and ``.when`` directly."""

    def test_rshift_two_transforms_builds_pipeline(self):
        pipeline = AddField("a", 1) >> AddField("b", 2)
        assert isinstance(pipeline, FactPipeline)
        assert pipeline({}) == {"a": 1, "b": 2}

    def test_rshift_is_ordered(self):
        # The right transform runs on the left's output (last write wins).
        pipeline = AddField("x", "first") >> AddField("x", "second")
        assert pipeline({})["x"] == "second"

    def test_rshift_chain_of_three(self):
        pipeline = AddField("a", 1) >> AddField("b", 2) >> AddField("c", 3)
        assert isinstance(pipeline, FactPipeline)
        assert pipeline({}) == {"a": 1, "b": 2, "c": 3}
        assert pipeline.inspect()["num_transforms"] == 3

    def test_rshift_transform_with_pipeline(self):
        # transform >> pipeline also works (mixed operands).
        pipeline = AddField("a", 1) >> FactPipeline([AddField("b", 2)])
        assert pipeline({}) == {"a": 1, "b": 2}

    def test_or_falls_back_on_error(self):
        pipeline = Boom() | AddField("recovered", True)
        assert pipeline({"k": "v"}) == {"k": "v", "recovered": True}

    def test_or_uses_first_when_it_succeeds(self):
        pipeline = AddField("a", 1) | AddField("b", 2)
        assert pipeline({}) == {"a": 1}

    def test_when_then_branch(self):
        pipeline = AddField("seen", True).when(
            lambda f: f.get("seen") is True,
            then=AddField("branch", "then"),
        )
        assert pipeline({})["branch"] == "then"

    def test_when_otherwise_branch(self):
        pipeline = DummyTransform().when(
            lambda f: f.get("missing") == "yes",
            then=AddField("branch", "then"),
            otherwise=AddField("branch", "else"),
        )
        assert pipeline({})["branch"] == "else"

    def test_composed_pipeline_is_serializable(self):
        pipeline = AddField("a", 1) >> AddField("b", 2)
        as_dict = pipeline.to_dict()
        assert set(as_dict) == {"name", "root"}

    def test_as_pipeline_uses_transform_class_name(self):
        pipeline = DummyTransform()._as_pipeline()
        assert pipeline.name == "DummyTransform"
        assert pipeline({}) == {"test": "pass"}

    def test_rshift_with_non_transform_raises_typeerror(self):
        with pytest.raises(TypeError, match="requires a Transform or FactPipeline"):
            AddField("a", 1) >> (lambda f: f)  # type: ignore[operator]

    def test_or_with_non_transform_raises_typeerror(self):
        with pytest.raises(TypeError, match="requires a Transform or FactPipeline"):
            AddField("a", 1) | (lambda f: f)  # type: ignore[operator]

    def test_pipeline_rshift_with_non_transform_raises_typeerror(self):
        pipeline = FactPipeline([AddField("a", 1)])
        with pytest.raises(TypeError, match="requires a Transform or FactPipeline"):
            pipeline >> (lambda f: f)  # type: ignore[operator]
