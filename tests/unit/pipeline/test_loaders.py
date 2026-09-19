"""Tests for fact sources and the FactLoader."""

from __future__ import annotations

import pytest

from fluxrules.pipeline.core import FactPipeline
from fluxrules.pipeline.error_policy import ErrorAction, ErrorPolicy
from fluxrules.pipeline.loaders import (
    CSVSource,
    FactLoader,
    IterableSource,
    JSONSource,
    ValidatedFactLoader,
)
from fluxrules.pipeline.schema import FactSchema
from fluxrules.pipeline.transforms.builtin import FieldType, Require
from fluxrules.pipeline.transforms.composed import Filter


class TestSources:
    def test_iterable_source(self):
        src = IterableSource([{"a": 1}, {"a": 2}])
        assert list(src.read()) == [{"a": 1}, {"a": 2}]

    def test_json_source_array(self):
        src = JSONSource('[{"a": 1}, {"a": 2}]')
        assert list(src.read()) == [{"a": 1}, {"a": 2}]

    def test_json_source_object(self):
        src = JSONSource('{"a": 1}')
        assert list(src.read()) == [{"a": 1}]

    def test_csv_source(self):
        src = CSVSource("a,b\n1,2\n3,4\n")
        rows = list(src.read())
        assert rows == [{"a": "1", "b": "2"}, {"a": "3", "b": "4"}]


class TestFactLoaderErrorPolicyString:
    def test_raise_propagates(self):
        loader = FactLoader(
            IterableSource([{"bad": 1}]),
            FactPipeline([Require(["amount"])]),
            on_error="raise",
        )
        with pytest.raises(ValueError):
            list(loader)

    def test_skip_drops_silently(self):
        loader = FactLoader(
            IterableSource([{"amount": 1}, {"bad": 1}]),
            FactPipeline([Require(["amount"])]),
            on_error="skip",
        )
        assert list(loader) == [{"amount": 1}]
        assert loader.dead_letter == []

    def test_collect_routes_to_dead_letter(self):
        loader = FactLoader(
            IterableSource([{"amount": 1}, {"bad": 1}]),
            FactPipeline([Require(["amount"])]),
            on_error="collect",
        )
        good = list(loader)
        assert good == [{"amount": 1}]
        assert len(loader.dead_letter) == 1
        assert "Missing required fields" in loader.dead_letter[0]["error"]


class TestFactLoaderBatching:
    def test_batches_evenly(self):
        loader = FactLoader(
            IterableSource([{"i": i} for i in range(4)]),
            FactPipeline([FieldType({"i": int})]),
        )
        batches = list(loader.batch(2))
        assert len(batches) == 2
        assert all(len(b) == 2 for b in batches)

    def test_final_partial_batch(self):
        loader = FactLoader(
            IterableSource([{"i": i} for i in range(5)]),
            FactPipeline([FieldType({"i": int})]),
        )
        batches = list(loader.batch(2))
        assert [len(b) for b in batches] == [2, 2, 1]

    def test_invalid_batch_size(self):
        loader = FactLoader(IterableSource([]), FactPipeline([FieldType({"i": int})]))
        with pytest.raises(ValueError, match="batch size"):
            list(loader.batch(0))


class TestFactLoaderErrorHandling:
    def test_error_policy_skip_drops_record(self):
        pipeline = FactPipeline(
            [Require(["amount"])],
            error_policy=ErrorPolicy(default=ErrorAction.SKIP),
        )
        loader = FactLoader(IterableSource([{"amount": 1}, {"bad": 1}]), pipeline)
        # Policy-driven skip leaves dead_letter empty (distinct from "collect").
        assert list(loader) == [{"amount": 1}]
        assert loader.dead_letter == []

    def test_filter_drops_facts(self):
        pipeline = FactPipeline([Filter(lambda f: f.get("age", 0) >= 18)])
        loader = FactLoader(IterableSource([{"age": 20}, {"age": 5}, {"age": 30}]), pipeline)
        assert list(loader) == [{"age": 20}, {"age": 30}]

    def test_error_policy_fallback(self):
        policy = ErrorPolicy(
            default=ErrorAction.FALLBACK,
            fallback_factory=lambda fact, err: {"recovered": True},
        )
        pipeline = FactPipeline([Require(["amount"])], error_policy=policy)
        loader = FactLoader(IterableSource([{"bad": 1}]), pipeline)
        assert list(loader) == [{"recovered": True}]


class TransactionFacts(FactSchema):
    user_id: str
    amount: float


class TestValidatedFactLoader:
    def test_schema_validates_before_pipeline(self):
        loader = ValidatedFactLoader(
            source=IterableSource([{"user_id": "u1", "amount": "10.5"}]),
            pipeline=FactPipeline([FieldType({"amount": float})]),
            schema=TransactionFacts,
        )
        assert list(loader) == [{"user_id": "u1", "amount": 10.5}]

    def test_collect_routes_schema_errors_to_dead_letter(self):
        loader = ValidatedFactLoader(
            source=IterableSource(
                [
                    {"user_id": "u1", "amount": "10.5"},
                    {"user_id": "u2"},
                ]
            ),
            pipeline=FactPipeline([Require(["user_id"])]),
            schema=TransactionFacts,
            on_error="collect",
        )
        assert list(loader) == [{"user_id": "u1", "amount": 10.5}]
        assert len(loader.dead_letter) == 1
        assert "schema validation failed" in loader.dead_letter[0]["error"]

    def test_skip_drops_schema_errors_silently(self):
        loader = ValidatedFactLoader(
            source=IterableSource([{"user_id": "u2"}]),
            pipeline=FactPipeline([Require(["user_id"])]),
            schema=TransactionFacts,
            on_error="skip",
        )
        assert list(loader) == []
        assert loader.dead_letter == []

    def test_schema_none_behaves_like_base_loader(self):
        loader = ValidatedFactLoader(
            source=IterableSource([{"amount": 1}, {"bad": 1}]),
            pipeline=FactPipeline([Require(["amount"])]),
            schema=None,
            on_error="collect",
        )
        assert list(loader) == [{"amount": 1}]
        assert len(loader.dead_letter) == 1
