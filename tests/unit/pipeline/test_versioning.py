"""Tests for pipeline versioning and breaking-change detection."""

from __future__ import annotations

from fluxrules.pipeline.core import FactPipeline
from fluxrules.pipeline.transforms.builtin import Defaults, Flatten, Require
from fluxrules.pipeline.versioning import (
    ChangeType,
    PipelineVersion,
    diff_pipelines,
)


class TestPipelineVersion:
    def test_from_pipeline_fingerprint_stable(self):
        p = FactPipeline([Flatten(), Defaults({"a": 1})])
        v1 = PipelineVersion.from_pipeline(p)
        v2 = PipelineVersion.from_pipeline(p)
        assert v1.fingerprint == v2.fingerprint

    def test_captures_fields(self):
        v = PipelineVersion.from_pipeline(FactPipeline([Defaults({"a": 1}), Require(["b"])]))
        assert "a" in v.output_fields
        assert "b" in v.required_input_fields

    def test_as_dict_serializable(self):
        import json

        v = PipelineVersion.from_pipeline(FactPipeline([Flatten()]))
        json.dumps(v.as_dict())


class TestDiff:
    def test_identical(self):
        p = FactPipeline([Defaults({"a": 1})])
        v = PipelineVersion.from_pipeline(p)
        assert diff_pipelines(v, v).change_type is ChangeType.IDENTICAL

    def test_additive_output_is_compatible(self):
        v1 = PipelineVersion.from_pipeline(FactPipeline([Defaults({"a": 1})]))
        v2 = PipelineVersion.from_pipeline(FactPipeline([Defaults({"a": 1, "b": 2})]))
        diff = diff_pipelines(v1, v2)
        assert diff.change_type is ChangeType.COMPATIBLE
        assert "b" in diff.added_outputs
        assert not diff.is_breaking

    def test_removed_output_is_breaking(self):
        v1 = PipelineVersion.from_pipeline(FactPipeline([Defaults({"a": 1, "b": 2})]))
        v2 = PipelineVersion.from_pipeline(FactPipeline([Defaults({"a": 1})]))
        diff = diff_pipelines(v1, v2)
        assert diff.change_type is ChangeType.BREAKING
        assert "b" in diff.removed_outputs
        assert diff.is_breaking

    def test_new_required_input_is_breaking(self):
        v1 = PipelineVersion.from_pipeline(FactPipeline([Require(["a"])]))
        v2 = PipelineVersion.from_pipeline(FactPipeline([Require(["a", "b"])]))
        diff = diff_pipelines(v1, v2)
        assert diff.change_type is ChangeType.BREAKING
        assert "b" in diff.added_required_inputs

    def test_reorder_is_breaking(self):
        v1 = PipelineVersion.from_pipeline(FactPipeline([Defaults({"a": 1}), Require(["a"])]))
        v2 = PipelineVersion.from_pipeline(FactPipeline([Require(["a"]), Defaults({"a": 1})]))
        assert diff_pipelines(v1, v2).change_type is ChangeType.BREAKING
