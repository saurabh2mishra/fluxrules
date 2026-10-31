"""Small paths this PR touched: unsupported fact types, the NOT-state
collector, the validation report text and the initialization log line."""

from __future__ import annotations

import logging

import pytest

from fluxrules import F, Rule
from fluxrules.engine.phreak import PhreakEngine
from fluxrules.engine.phreak._engine import _collect_not_states
from fluxrules.pipeline.validators import InvalidFactError
from fluxrules.services.validators.base import SeverityLevel, ValidationResult


def _engine() -> PhreakEngine:
    engine = PhreakEngine()
    engine.load_rules([Rule(id=1, name="r", conditions=F("amount") > 1, action="x")])
    return engine


class TestUnsupportedFacts:
    def test_unsupported_fact_type_raises_type_error(self):
        with pytest.raises(TypeError, match="facts must be a dict or a model"):
            _engine().evaluate(object())

    def test_strict_facts_reports_it_as_an_invalid_fact(self):
        with pytest.raises(InvalidFactError):
            _engine().evaluate(object(), strict_facts=True)


def test_not_state_collector_ignores_non_tree_values():
    states: dict = {}
    _collect_not_states(None, states)
    _collect_not_states(["junk", 3], states)
    assert states == {}


class TestValidationReportText:
    def test_no_issues(self):
        assert str(ValidationResult()) == "✓ No validation issues"

    def test_with_issues(self):
        result = ValidationResult()
        result.add_issue("bad_op", "Unknown operator", SeverityLevel.ERROR)
        text = str(result)
        assert text.startswith("Validation Report (1 issues):")
        assert "Unknown operator" in text


def test_initialize_without_persistence_logs_success(caplog):
    from fluxrules.initialization import initialize_fluxrules

    with caplog.at_level(logging.INFO, logger="fluxrules.initialization"):
        initialize_fluxrules(enable_persistence=False)
    assert "FluxRules initialized successfully" in caplog.text
