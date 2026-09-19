"""Tests for FactPipeline core: composition, inspection, serialization."""

from __future__ import annotations

from typing import Any

import pytest

from fluxrules.pipeline.base import Transform, TransformMetadata
from fluxrules.pipeline.core import (
    CompositionNode,
    CompositionOperator,
    FactPipeline,
)
from fluxrules.pipeline.transforms.builtin import Defaults, Flatten, Rename, Require


class AddKey(Transform):
    """Transform that sets a single key to a constant value."""

    def __init__(self, key: str, value: Any) -> None:
        self.key = key
        self.value = value

    def __call__(self, fact: dict[str, Any]) -> dict[str, Any]:
        out = dict(fact)
        out[self.key] = self.value
        return out

    @property
    def metadata(self) -> TransformMetadata:
        return TransformMetadata(name=f"Add[{self.key}]", output_fields=[self.key])


class Boom(Transform):
    """Transform that always raises ValueError."""

    def __call__(self, fact: dict[str, Any]) -> dict[str, Any]:
        raise ValueError("boom")

    @property
    def metadata(self) -> TransformMetadata:
        return TransformMetadata(name="Boom", errors_raised=[ValueError])


class TestConstruction:
    def test_single_transform(self):
        p = FactPipeline([AddKey("a", 1)])
        assert p({}) == {"a": 1}

    def test_multiple_transforms_sequence(self):
        p = FactPipeline([AddKey("a", 1), AddKey("b", 2)])
        assert p({}) == {"a": 1, "b": 2}

    def test_empty_transforms_raises(self):
        with pytest.raises(ValueError, match="at least one transform"):
            FactPipeline([])

    def test_no_args_raises(self):
        with pytest.raises(ValueError, match="Either transforms or root"):
            FactPipeline()

    def test_root_construction(self):
        node = CompositionNode(
            op=CompositionOperator.SEQUENCE,
            left=AddKey("a", 1),
            right=AddKey("b", 2),
        )
        p = FactPipeline(root=node)
        assert p({}) == {"a": 1, "b": 2}


class TestCompositionOperators:
    def test_sequence_operator(self):
        p = FactPipeline([AddKey("a", 1)]) >> FactPipeline([AddKey("b", 2)])
        assert p({}) == {"a": 1, "b": 2}

    def test_sequence_with_bare_transform(self):
        p = FactPipeline([AddKey("a", 1)]) >> AddKey("b", 2)
        assert p({}) == {"a": 1, "b": 2}

    def test_union_falls_back_on_error(self):
        p = FactPipeline([Boom()]) | FactPipeline([AddKey("fallback", True)])
        assert p({}) == {"fallback": True}

    def test_union_uses_left_on_success(self):
        p = FactPipeline([AddKey("a", 1)]) | FactPipeline([AddKey("b", 2)])
        assert p({}) == {"a": 1}

    def test_when_true_branch(self):
        p = FactPipeline([AddKey("base", 1)]).when(
            lambda f: f.get("base") == 1,
            then=AddKey("hit", True),
        )
        assert p({}) == {"base": 1, "hit": True}

    def test_when_false_branch_passthrough(self):
        p = FactPipeline([AddKey("base", 0)]).when(
            lambda f: f.get("base") == 1,
            then=AddKey("hit", True),
        )
        assert p({}) == {"base": 0}

    def test_when_else_branch(self):
        p = FactPipeline([AddKey("base", 0)]).when(
            lambda f: f.get("base") == 1,
            then=AddKey("hit", True),
            otherwise=AddKey("miss", True),
        )
        assert p({}) == {"base": 0, "miss": True}

    def test_chained_composition(self):
        p = FactPipeline([AddKey("a", 1)]) >> AddKey("b", 2) >> AddKey("c", 3)
        assert p({}) == {"a": 1, "b": 2, "c": 3}


class TestIntrospection:
    def test_inspect_counts_transforms(self):
        p = FactPipeline([Flatten(), Rename({"id": ["x"]}), Require(["id"])])
        spec = p.inspect()
        assert spec["num_transforms"] == 3
        assert len(spec["transforms"]) == 3

    def test_inspect_aggregates_fields(self):
        p = FactPipeline([Rename({"id": ["x"]}), Defaults({"country": "US"})])
        agg = p.inspect()["aggregated"]
        assert "id" in agg["all_output_fields"]
        assert "country" in agg["all_output_fields"]
        assert "x" in agg["all_input_fields"]

    def test_inspect_collects_errors(self):
        p = FactPipeline([Require(["id"])])
        agg = p.inspect()["aggregated"]
        assert "ValueError" in agg["all_errors"]

    def test_transforms_returns_in_order(self):
        t1, t2, t3 = AddKey("a", 1), AddKey("b", 2), AddKey("c", 3)
        p = FactPipeline([t1, t2, t3])
        assert p.transforms() == [t1, t2, t3]

    def test_inspect_includes_signature(self):
        p = FactPipeline([Flatten()])
        assert "signature" in p.inspect()["transforms"][0]


class TestSerialization:
    def test_to_dict_is_json_serializable(self):
        import json

        p = FactPipeline([Flatten(), Rename({"id": ["x"]})])
        json.dumps(p.to_dict())  # must not raise

    def test_to_dict_structure(self):
        p = FactPipeline([Flatten()])
        d = p.to_dict()
        assert d["name"] == "default"
        assert d["root"]["type"] == "Flatten"

    def test_to_dict_composition_node(self):
        p = FactPipeline([Flatten(), Defaults({"a": 1})])
        root = p.to_dict()["root"]
        assert root["type"] == "composition"
        assert root["op"] == "seq"

    def test_round_trip_with_default_registry(self):
        original = FactPipeline(
            [Flatten(), Rename({"id": ["x"]}), Defaults({"a": 1}), Require(["id"])]
        )
        spec = original.to_dict()
        rebuilt = FactPipeline.from_dict(spec)
        fact = {"x": "v"}
        assert rebuilt(dict(fact)) == original(dict(fact))

    def test_repr(self):
        p = FactPipeline([Flatten(), Defaults({"a": 1})])
        assert "FactPipeline" in repr(p)
        assert "transforms=2" in repr(p)
