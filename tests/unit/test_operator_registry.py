"""Tests for the custom operator registry."""

import pytest

from fluxrules.domain.errors import UnknownOperatorError
from fluxrules.engine.operator_registry import (
    OperatorRegistry,
    get_operator_registry,
    register_operator,
)


class TestOperatorRegistry:
    """Tests for custom operator registration."""

    def test_register_and_get(self):
        reg = OperatorRegistry()
        reg.register("is_even", lambda val, _: val % 2 == 0)
        func = reg.get("is_even")
        assert func(4, None) is True
        assert func(3, None) is False

    def test_get_unknown_raises(self):
        reg = OperatorRegistry()
        with pytest.raises(UnknownOperatorError, match="not registered"):
            reg.get("nonexistent")

    def test_has(self):
        reg = OperatorRegistry()
        reg.register("custom_op", lambda a, b: True)
        assert reg.has("custom_op") is True
        assert reg.has("other") is False

    def test_unregister(self):
        reg = OperatorRegistry()
        reg.register("temp", lambda a, b: True)
        reg.unregister("temp")
        assert reg.has("temp") is False

    def test_list_operators(self):
        reg = OperatorRegistry()
        reg.register("op_b", lambda a, b: True)
        reg.register("op_a", lambda a, b: True)
        assert reg.list_operators() == ["op_a", "op_b"]

    def test_clear(self):
        reg = OperatorRegistry()
        reg.register("x", lambda a, b: True)
        reg.clear()
        assert reg.list_operators() == []

    def test_register_non_callable_raises(self):
        reg = OperatorRegistry()
        with pytest.raises(TypeError, match="callable"):
            reg.register("bad", "not_a_function")  # type: ignore

    def test_module_level_register(self):
        register_operator("global_test_op", lambda a, b: a == b)
        reg = get_operator_registry()
        assert reg.has("global_test_op")
        reg.unregister("global_test_op")
