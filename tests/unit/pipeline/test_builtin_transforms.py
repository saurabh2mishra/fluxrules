"""Tests for the stock builtin transforms."""

from __future__ import annotations

import pytest

from fluxrules.pipeline.transforms.builtin import (
    Defaults,
    FieldType,
    Flatten,
    Rename,
    Require,
)


class TestFlatten:
    def test_nested_dict(self):
        assert Flatten()({"user": {"age": 25}}) == {"user.age": 25}

    def test_deeply_nested(self):
        out = Flatten()({"a": {"b": {"c": 1}}})
        assert out == {"a.b.c": 1}

    def test_first_list_item_only(self):
        out = Flatten()({"items": [{"x": 1}, {"x": 2}]})
        assert out == {"items[0].x": 1}

    def test_custom_separator(self):
        assert Flatten(sep="/")({"a": {"b": 1}}) == {"a/b": 1}

    def test_metadata(self):
        meta = Flatten().metadata
        assert meta.name == "Flatten"
        assert meta.errors_raised == []

    def test_round_trip(self):
        original = Flatten(sep="/")
        rebuilt = Flatten.from_dict(original.to_dict())
        assert rebuilt.sep == "/"


class TestRename:
    def test_first_alias_wins(self):
        t = Rename({"user_id": ["user.id", "userId"]})
        assert t({"user.id": "a", "userId": "b"})["user_id"] == "a"

    def test_second_alias_used_when_first_absent(self):
        t = Rename({"user_id": ["user.id", "userId"]})
        assert t({"userId": "b"})["user_id"] == "b"

    def test_keeps_original_keys(self):
        t = Rename({"user_id": ["userId"]})
        out = t({"userId": "b"})
        assert out["userId"] == "b"
        assert out["user_id"] == "b"

    def test_missing_alias_no_output(self):
        t = Rename({"user_id": ["userId"]})
        assert "user_id" not in t({"other": 1})

    def test_metadata_fields(self):
        meta = Rename({"user_id": ["a", "b"]}).metadata
        assert set(meta.output_fields) == {"user_id"}
        assert set(meta.required_input_fields) == {"a", "b"}

    def test_round_trip(self):
        original = Rename({"id": ["x", "y"]})
        rebuilt = Rename.from_dict(original.to_dict())
        assert rebuilt.mapping == {"id": ["x", "y"]}


class TestFieldType:
    def test_int_conversion(self):
        assert FieldType({"age": int})({"age": "25"}) == {"age": 25}

    def test_float_conversion(self):
        assert FieldType({"amount": float})({"amount": "12.5"}) == {"amount": 12.5}

    def test_lambda_conversion(self):
        t = FieldType({"amount": lambda c: float(c) / 100})
        assert t({"amount": "250"}) == {"amount": 2.5}

    def test_skips_missing_field(self):
        assert FieldType({"age": int})({"other": 1}) == {"other": 1}

    def test_skips_empty_string(self):
        assert FieldType({"age": int})({"age": ""}) == {"age": ""}

    def test_skips_none(self):
        assert FieldType({"age": int})({"age": None}) == {"age": None}

    def test_invalid_raises_value_error(self):
        with pytest.raises(ValueError, match="FieldType failed for field 'age'"):
            FieldType({"age": int})({"age": "not-a-number"})

    def test_metadata_declares_errors(self):
        meta = FieldType({"age": int}).metadata
        assert ValueError in meta.errors_raised
        assert TypeError in meta.errors_raised

    def test_round_trip_builtin_converter(self):
        original = FieldType({"age": int, "amount": float})
        rebuilt = FieldType.from_dict(original.to_dict())
        assert rebuilt({"age": "3", "amount": "1.5"}) == {"age": 3, "amount": 1.5}

    def test_round_trip_custom_converter_raises(self):
        original = FieldType({"amount": lambda c: float(c) / 100})
        with pytest.raises(ValueError, match="custom converter"):
            FieldType.from_dict(original.to_dict())


class TestDefaults:
    def test_fills_missing(self):
        assert Defaults({"country": "US"})({"amount": 1}) == {
            "country": "US",
            "amount": 1,
        }

    def test_does_not_clobber_present(self):
        assert Defaults({"country": "US"})({"country": "NG"})["country"] == "NG"

    def test_metadata(self):
        assert Defaults({"a": 1}).metadata.output_fields == ["a"]

    def test_round_trip(self):
        original = Defaults({"a": 1, "b": 2})
        rebuilt = Defaults.from_dict(original.to_dict())
        assert rebuilt.defaults == {"a": 1, "b": 2}


class TestRequire:
    def test_passes_when_present(self):
        assert Require(["a"])({"a": 1}) == {"a": 1}

    def test_raises_when_missing(self):
        with pytest.raises(ValueError, match="Missing required fields"):
            Require(["a"])({"b": 2})

    def test_raises_on_none(self):
        with pytest.raises(ValueError):
            Require(["a"])({"a": None})

    def test_raises_on_empty_string(self):
        with pytest.raises(ValueError):
            Require(["a"])({"a": ""})

    def test_metadata(self):
        meta = Require(["a", "b"]).metadata
        assert meta.required_input_fields == ["a", "b"]
        assert ValueError in meta.errors_raised

    def test_round_trip(self):
        original = Require(["a", "b"])
        rebuilt = Require.from_dict(original.to_dict())
        assert rebuilt.fields == ["a", "b"]
