"""Tests for flatten_dict (utils)."""

from __future__ import annotations

import pytest

from fluxrules.pipeline.utils.dict_utils import (
    ListStrategy,
    flatten_dict,
)


class TestFlattenDict:
    def test_flat_passthrough(self):
        assert flatten_dict({"a": 1}) == {"a": 1}

    def test_nested(self):
        assert flatten_dict({"a": {"b": {"c": 1}}}) == {"a.b.c": 1}

    def test_first_list_item(self):
        assert flatten_dict({"items": [{"x": 1}, {"x": 2}]}) == {"items[0].x": 1}

    def test_scalar_list_kept(self):
        # V1 keeps scalar lists as-is (only lists of dicts trigger flattening).
        assert flatten_dict({"tags": ["a", "b"]}) == {"tags": ["a", "b"]}

    def test_custom_separator(self):
        assert flatten_dict({"a": {"b": 1}}, sep="/") == {"a/b": 1}


class TestFlattenDictStrategies:
    def test_first_only(self):
        out = flatten_dict({"items": [{"x": 1}, {"x": 2}]}, list_strategy=ListStrategy.FIRST_ONLY)
        assert out == {"items[0].x": 1}

    def test_all_with_index(self):
        out = flatten_dict(
            {"items": [{"x": 1}, {"x": 2}]},
            list_strategy=ListStrategy.ALL_WITH_INDEX,
        )
        assert out == {"items[0].x": 1, "items[1].x": 2}

    def test_all_with_index_scalars(self):
        out = flatten_dict({"tags": ["a", "b"]}, list_strategy=ListStrategy.ALL_WITH_INDEX)
        assert out == {"tags[0]": "a", "tags[1]": "b"}

    def test_merge_all(self):
        out = flatten_dict({"items": [{"x": 1}, {"y": 2}]}, list_strategy=ListStrategy.MERGE_ALL)
        assert out == {"items.x": 1, "items.y": 2}

    def test_keep_as_list(self):
        out = flatten_dict({"tags": ["a", "b"]}, list_strategy=ListStrategy.KEEP_AS_LIST)
        assert out == {"tags": ["a", "b"]}

    def test_comma_separated(self):
        out = flatten_dict({"tags": ["a", "b"]}, list_strategy=ListStrategy.COMMA_SEPARATED)
        assert out == {"tags": "a,b"}

    def test_json_encoded(self):
        out = flatten_dict({"tags": ["a", "b"]}, list_strategy=ListStrategy.JSON_ENCODED)
        assert out == {"tags": '["a", "b"]'}

    def test_drop(self):
        out = flatten_dict({"tags": ["a", "b"], "x": 1}, list_strategy=ListStrategy.DROP)
        assert out == {"x": 1}


class TestFlattenDictSafety:
    def test_cycle_detection(self):
        data: dict = {"a": 1}
        data["self"] = data
        with pytest.raises(ValueError, match="circular reference"):
            flatten_dict(data)

    def test_max_depth(self):
        deep: dict = {"v": 1}
        for _ in range(10):
            deep = {"n": deep}
        with pytest.raises(ValueError, match="max_depth"):
            flatten_dict(deep, max_depth=3)

    def test_within_depth_ok(self):
        out = flatten_dict({"a": {"b": {"c": 1}}}, max_depth=5)
        assert out == {"a.b.c": 1}
