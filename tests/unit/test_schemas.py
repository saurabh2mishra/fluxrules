"""Tests for core typed schema definitions."""

from __future__ import annotations

import pytest

from fluxrules.domain.schemas import (
    AccumulateConfig,
    EngineConfig,
    EvaluationContext,
    RuleDefinition,
)


class TestRuleDefinition:
    """Validate RuleDefinition dataclass."""

    def test_valid_rule(self) -> None:
        """A valid rule should initialise without error."""
        rule = RuleDefinition(
            id="r1",
            name="test",
            conditions=[{"field": "age", "op": ">", "value": 18}],
            actions=[{"type": "flag"}],
        )
        assert rule.priority == 100

    def test_empty_id_rejected(self) -> None:
        """An empty id should raise ValueError."""
        with pytest.raises(ValueError, match="ID"):
            RuleDefinition(id="", name="x", conditions=[{"a": 1}], actions=[{"b": 2}])

    def test_empty_conditions_rejected(self) -> None:
        """Empty conditions should raise ValueError."""
        with pytest.raises(ValueError, match="condition"):
            RuleDefinition(id="r1", name="x", conditions=[], actions=[{"b": 2}])

    def test_empty_actions_rejected(self) -> None:
        """Empty actions should raise ValueError."""
        with pytest.raises(ValueError, match="action"):
            RuleDefinition(id="r1", name="x", conditions=[{"a": 1}], actions=[])


class TestEvaluationContext:
    """Validate EvaluationContext defaults."""

    def test_defaults(self) -> None:
        """Trace and metadata should default to empty."""
        ctx = EvaluationContext(facts={"x": 1})
        assert ctx.trace == []
        assert ctx.metadata == {}


class TestAccumulateConfig:
    """Validate AccumulateConfig."""

    def test_defaults(self) -> None:
        """Result binding should default to 'result'."""
        cfg = AccumulateConfig(function="sum", field="amount")
        assert cfg.result_binding == "result"
        assert cfg.constraint is None


class TestEngineConfig:
    """Validate EngineConfig defaults."""

    def test_defaults(self) -> None:
        """Engine type should default to PHREAK."""
        cfg = EngineConfig()
        assert cfg.engine_type == "PHREAK"
        assert cfg.enable_metrics is False
