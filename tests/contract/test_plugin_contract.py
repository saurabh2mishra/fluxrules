"""Contract tests for the real FluxRules extension points.

These replace the previous ``PluginRegistry`` stub test (which only checked that
a dict stored a value). Each test here exercises an extension point that is
actually wired into evaluation or selection: custom operators, custom engines
via :func:`fluxrules.register_engine`, entry-point auto-discovery, and the
public engine conformance kit.
"""

from __future__ import annotations

import pytest

from fluxrules import (
    get_available_engines,
    get_engine,
    register_engine,
    register_operator,
    unregister_engine,
)
from fluxrules.engine.base import BaseEngine
from fluxrules.engine.operator_registry import get_operator_registry
from fluxrules.engine.phreak import PhreakEngine
from fluxrules.testing import assert_engine_contract


class _CustomEngine(PhreakEngine):
    """A trivial custom engine: behaves like PHREAK, different selector name."""


def test_custom_operator_is_registered_and_callable() -> None:
    register_operator("within_range", lambda val, spec: spec[0] <= val <= spec[1])
    registry = get_operator_registry()
    assert registry.has("within_range")
    assert registry.get("within_range")(42, [10, 50]) is True


def test_register_engine_makes_it_selectable_end_to_end() -> None:
    register_engine("MYENGINE", _CustomEngine)
    try:
        assert "MYENGINE" in get_available_engines()
        engine = get_engine("myengine")  # case-insensitive
        assert isinstance(engine, _CustomEngine)
        assert isinstance(engine, BaseEngine)
    finally:
        unregister_engine("MYENGINE")
    assert "MYENGINE" not in get_available_engines()


def test_register_engine_rejects_non_engine() -> None:
    with pytest.raises(TypeError):
        register_engine("BAD", object)  # type: ignore[arg-type]


def test_builtin_engine_cannot_be_overridden_or_removed() -> None:
    with pytest.raises(ValueError):
        register_engine("PHREAK", _CustomEngine, override=True)
    with pytest.raises(ValueError):
        unregister_engine("PHREAK")


def test_duplicate_registration_requires_override() -> None:
    register_engine("DUP", _CustomEngine)
    try:
        with pytest.raises(ValueError):
            register_engine("DUP", _CustomEngine)
        register_engine("DUP", _CustomEngine, override=True)  # allowed
    finally:
        unregister_engine("DUP")


def test_shipped_engine_satisfies_the_reference_contract() -> None:
    # The public conformance kit must pass for FluxRules' own engine.
    assert_engine_contract(PhreakEngine)


def test_entry_point_discovery_registers_operator(monkeypatch) -> None:
    from fluxrules.plugins import discovery

    class _FakeEP:
        name = "ep_double"

        @staticmethod
        def load():
            return lambda val, spec: val == spec * 2

    monkeypatch.setattr(
        discovery,
        "_iter_entry_points",
        lambda group: [_FakeEP()] if group == "fluxrules.operators" else [],
    )

    loaded = discovery.load_plugins(groups=("fluxrules.operators",))
    try:
        assert loaded == {"fluxrules.operators": ["ep_double"]}
        assert get_operator_registry().has("ep_double")
    finally:
        get_operator_registry().unregister("ep_double")


def test_entry_point_discovery_registers_engine(monkeypatch) -> None:
    from fluxrules.plugins import discovery

    class _FakeEP:
        name = "EPENGINE"

        @staticmethod
        def load():
            return _CustomEngine

    monkeypatch.setattr(
        discovery,
        "_iter_entry_points",
        lambda group: [_FakeEP()] if group == "fluxrules.engines" else [],
    )

    loaded = discovery.load_plugins(groups=("fluxrules.engines",))
    try:
        assert loaded == {"fluxrules.engines": ["EPENGINE"]}
        assert isinstance(get_engine("EPENGINE"), _CustomEngine)
    finally:
        unregister_engine("EPENGINE")


def test_entry_point_discovery_skips_failing_plugin(monkeypatch) -> None:
    from fluxrules.plugins import discovery

    class _BadEP:
        name = "boom"

        @staticmethod
        def load():
            raise RuntimeError("plugin blew up")

    monkeypatch.setattr(
        discovery,
        "_iter_entry_points",
        lambda group: [_BadEP()] if group == "fluxrules.operators" else [],
    )

    loaded = discovery.load_plugins(groups=("fluxrules.operators",))
    assert loaded == {"fluxrules.operators": []}  # failure logged, not raised
