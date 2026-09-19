"""Tests for observability hooks and metrics."""

from __future__ import annotations

import logging
from typing import Any

from fluxrules.pipeline.base import Transform, TransformMetadata
from fluxrules.pipeline.core import FactPipeline
from fluxrules.pipeline.observability import (
    LoggingHook,
    MetricsHook,
    PipelineMetrics,
)
from fluxrules.pipeline.transforms.builtin import Defaults, Require


class Boom(Transform):
    def __call__(self, fact: dict[str, Any]) -> dict[str, Any]:
        raise ValueError("boom")

    @property
    def metadata(self) -> TransformMetadata:
        return TransformMetadata(name="Boom", errors_raised=[ValueError])


class RecordingHook:
    """Hook that records the sequence of callbacks it receives."""

    def __init__(self) -> None:
        self.events: list[str] = []

    def on_pipeline_start(self, pipeline_name: str, fact: dict[str, Any]) -> None:
        self.events.append("pipeline_start")

    def on_transform_start(self, transform: Transform, fact: dict[str, Any]) -> None:
        self.events.append(f"transform_start:{transform.metadata.name}")

    def on_transform_end(self, transform: Transform, fact: dict[str, Any], duration: float) -> None:
        self.events.append(f"transform_end:{transform.metadata.name}")

    def on_transform_error(
        self, transform: Transform, fact: dict[str, Any], error: Exception
    ) -> None:
        self.events.append(f"transform_error:{transform.metadata.name}")

    def on_pipeline_end(self, pipeline_name: str, fact: dict[str, Any], duration: float) -> None:
        self.events.append("pipeline_end")

    def on_pipeline_error(self, pipeline_name: str, fact: dict[str, Any], error: Exception) -> None:
        self.events.append("pipeline_error")


class TestHookInvocation:
    def test_success_event_order(self):
        hook = RecordingHook()
        pipeline = FactPipeline([Defaults({"a": 1})], hooks=[hook])
        pipeline({})
        assert hook.events == [
            "pipeline_start",
            "transform_start:Defaults",
            "transform_end:Defaults",
            "pipeline_end",
        ]

    def test_error_events(self):
        hook = RecordingHook()
        pipeline = FactPipeline([Boom()], hooks=[hook])
        try:
            pipeline({})
        except ValueError:
            pass
        assert "transform_error:Boom" in hook.events
        assert "pipeline_error" in hook.events

    def test_partial_hook_is_tolerated(self):
        class PartialHook:
            def __init__(self) -> None:
                self.count = 0

            def on_pipeline_end(self, name: str, fact: dict[str, Any], d: float) -> None:
                self.count += 1

        hook = PartialHook()
        FactPipeline([Defaults({"a": 1})], hooks=[hook])({})
        assert hook.count == 1


class TestMetricsHook:
    def test_records_pipeline_runs(self):
        metrics = PipelineMetrics()
        pipeline = FactPipeline([Defaults({"a": 1})], hooks=[MetricsHook(metrics)])
        pipeline({})
        pipeline({})
        assert metrics.pipeline_runs == 2

    def test_records_transform_invocations(self):
        metrics = PipelineMetrics()
        pipeline = FactPipeline(
            [Defaults({"a": 1}), Defaults({"b": 2})], hooks=[MetricsHook(metrics)]
        )
        pipeline({})
        assert metrics.transform_invocations["Defaults"] == 2

    def test_records_pipeline_errors(self):
        metrics = PipelineMetrics()
        pipeline = FactPipeline([Boom()], hooks=[MetricsHook(metrics)])
        try:
            pipeline({})
        except ValueError:
            pass
        assert metrics.pipeline_errors == 1
        assert metrics.transform_errors["Boom"] == 1

    def test_avg_duration_zero_when_no_runs(self):
        assert PipelineMetrics().avg_pipeline_duration == 0.0

    def test_as_dict_is_serializable(self):
        import json

        metrics = PipelineMetrics()
        FactPipeline([Defaults({"a": 1})], hooks=[MetricsHook(metrics)])({})
        json.dumps(metrics.as_dict())


class TestLoggingHook:
    def test_logs_without_error(self, caplog):
        with caplog.at_level(logging.DEBUG, logger="fluxrules.pipeline"):
            pipeline = FactPipeline([Defaults({"a": 1})], hooks=[LoggingHook()])
            pipeline({})
        assert any("pipeline_start" in r.message for r in caplog.records)

    def test_logs_error(self, caplog):
        with caplog.at_level(logging.ERROR, logger="fluxrules.pipeline"):
            pipeline = FactPipeline([Require(["x"])], hooks=[LoggingHook()])
            try:
                pipeline({})
            except ValueError:
                pass
        assert any("transform_error" in r.message for r in caplog.records)
