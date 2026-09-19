"""Tests for optional strict fact pre-flight validation in engine.evaluate()."""

from __future__ import annotations

import pytest

from fluxrules.engine.phreak import PhreakEngine
from fluxrules.pipeline.validators import InvalidFactError


def test_evaluate_default_allows_nested_facts() -> None:
    """strict_facts defaults to False for backward-compatible behavior."""
    engine = PhreakEngine()
    result = engine.evaluate({"user": {"id": "u1"}})
    assert result.fired_rules == []


def test_evaluate_strict_facts_rejects_nested_dict() -> None:
    engine = PhreakEngine()
    with pytest.raises(InvalidFactError, match="facts must be flat"):
        engine.evaluate({"user": {"id": "u1"}}, strict_facts=True)


def test_evaluate_strict_facts_rejects_nested_list() -> None:
    engine = PhreakEngine()
    with pytest.raises(InvalidFactError, match="facts must be flat"):
        engine.evaluate({"tags": ["vip", "new"]}, strict_facts=True)


def test_evaluate_strict_facts_rejects_non_dict() -> None:
    engine = PhreakEngine()
    with pytest.raises(InvalidFactError, match="result must be a dict"):
        engine.evaluate([("a", 1)], strict_facts=True)  # type: ignore[arg-type]
