"""Tests for advanced/composed transforms."""

from __future__ import annotations

import pytest

from fluxrules.pipeline.transforms.builtin import Defaults, Rename, Require
from fluxrules.pipeline.transforms.composed import (
    Conditional,
    DropFact,
    Filter,
    MapValues,
    Switch,
)


class TestConditional:
    def test_then_branch(self):
        t = Conditional(
            lambda f: f.get("source") == "legacy",
            then_transform=Defaults({"legacy": True}),
            else_transform=Defaults({"modern": True}),
        )
        assert t({"source": "legacy"}) == {"source": "legacy", "legacy": True}

    def test_else_branch(self):
        t = Conditional(
            lambda f: f.get("source") == "legacy",
            then_transform=Defaults({"legacy": True}),
            else_transform=Defaults({"modern": True}),
        )
        assert t({"source": "new"}) == {"source": "new", "modern": True}

    def test_no_else_passthrough(self):
        t = Conditional(lambda f: False, then_transform=Defaults({"x": 1}))
        assert t({"a": 1}) == {"a": 1}

    def test_metadata_merges_branches(self):
        t = Conditional(
            lambda f: True,
            then_transform=Rename({"a": ["x"]}),
            else_transform=Rename({"b": ["y"]}),
        )
        outputs = set(t.metadata.output_fields)
        assert {"a", "b"} <= outputs

    def test_metadata_then_only(self):
        t = Conditional(lambda f: True, then_transform=Rename({"a": ["x"]}))
        assert t.metadata.output_fields == ["a"]
        assert t.metadata.name == "Conditional"


class TestFilter:
    def test_passes_matching(self):
        assert Filter(lambda f: f["age"] >= 18)({"age": 20}) == {"age": 20}

    def test_drops_non_matching(self):
        with pytest.raises(DropFact):
            Filter(lambda f: f["age"] >= 18)({"age": 5})

    def test_metadata_declares_dropfact(self):
        assert DropFact in Filter(lambda f: True).metadata.errors_raised


class TestSwitch:
    def test_first_match_wins(self):
        t = Switch(
            [
                (lambda f: f["k"] == "a", Defaults({"branch": "a"})),
                (lambda f: f["k"] == "b", Defaults({"branch": "b"})),
            ]
        )
        assert t({"k": "b"})["branch"] == "b"

    def test_default_used(self):
        t = Switch(
            [(lambda f: f["k"] == "a", Defaults({"branch": "a"}))],
            default=Defaults({"branch": "default"}),
        )
        assert t({"k": "z"})["branch"] == "default"

    def test_no_match_no_default_passthrough(self):
        t = Switch([(lambda f: False, Defaults({"x": 1}))])
        assert t({"a": 1}) == {"a": 1}


class TestSwitchMetadata:
    def test_metadata_aggregates_cases_and_default(self):
        t = Switch(
            [(lambda f: True, Defaults({"a": 1}))],
            default=Require(["b"]),
        )
        meta = t.metadata
        assert meta.name == "Switch"
        assert "a" in meta.output_fields
        assert ValueError in meta.errors_raised


class TestMapValues:
    def test_specific_fields(self):
        assert MapValues(str.strip, fields=["name"])({"name": "  bob "}) == {"name": "bob"}

    def test_all_fields(self):
        out = MapValues(lambda v: v * 2)({"a": 1, "b": 2})
        assert out == {"a": 2, "b": 4}

    def test_missing_field_ignored(self):
        assert MapValues(str.upper, fields=["missing"])({"a": "x"}) == {"a": "x"}

    def test_metadata(self):
        meta = MapValues(str.strip, fields=["name"]).metadata
        assert meta.name == "MapValues"
        assert meta.output_fields == ["name"]

    def test_metadata_all_fields_empty(self):
        meta = MapValues(str.strip).metadata
        assert meta.output_fields == []
