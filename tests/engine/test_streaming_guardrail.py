"""Streaming-misuse guardrail tests (PHREAK P2.5).

Streaming mode returns the activation *delta* and is order-dependent (requires
sticky routing). Serving it behind the stateless HTTP request/response path
silently breaks the "every matching rule, every request" expectation (§5.3).
These tests pin:

- ``engine.mode`` surfaces the live contract (stateless vs streaming),
- the API adapter logs a one-time warning when a streaming engine is served
  behind the stateless path,
- dedup rejects streaming engines (covered more fully in tests/engine/test_dedup).
"""

from __future__ import annotations

import logging

import pytest

from fluxrules import Rule
from fluxrules.engine.phreak._engine import PhreakEngine
from fluxrules.engine.runtime import DedupEvaluator


def _leaf(rid: int) -> Rule:
    return Rule(
        id=rid,
        name=f"r{rid}",
        condition_dsl={"type": "condition", "field": "amount", "op": ">", "value": 5},
        tags=frozenset(),
        persist=False,
    )


class TestEngineModeSurface:
    def test_stateless_mode_string(self):
        engine = PhreakEngine()
        assert engine.mode == "stateless"

    def test_streaming_mode_string(self):
        engine = PhreakEngine(streaming_mode=True)
        assert engine.mode == "streaming"

    def test_mode_in_observability(self):
        engine = PhreakEngine(streaming_mode=True, enable_metrics=True)
        engine.load_rules([_leaf(1)])
        assert engine.get_observability_metrics()["mode"] == "streaming"


class TestStreamingDeltaSemantics:
    """Repeated facts return an empty delta - the §5.3 trap, made explicit."""

    def test_repeated_fact_returns_empty_delta(self):
        engine = PhreakEngine(streaming_mode=True)
        engine.load_rules([_leaf(1)])

        first = engine.evaluate({"amount": 10})
        assert 1 in first.fired_rules  # first time: fires

        second = engine.evaluate({"amount": 10})  # identical fact
        assert second.fired_rules == []  # delta is empty - NOT "stopped firing"

    def test_stateless_refires_every_call(self):
        engine = PhreakEngine(streaming_mode=False)
        engine.load_rules([_leaf(1)])
        r1 = engine.evaluate({"amount": 10})
        r2 = engine.evaluate({"amount": 10})
        assert 1 in r1.fired_rules
        assert 1 in r2.fired_rules  # stateless: every matching rule, every call


class TestDedupRejectsStreaming:
    def test_dedup_rejects_streaming_engine(self):
        engine = PhreakEngine(streaming_mode=True)
        engine.load_rules([_leaf(1)])
        with pytest.raises(ValueError):
            DedupEvaluator(engine)


class TestAdapterStreamingWarning:
    """The API adapter warns once when a streaming engine is on the HTTP path."""

    def test_warns_once_via_engine_holder(self, caplog):
        # Build the adapter without a DB, then point its holder at a streaming
        # engine to simulate the misuse (streaming behind the stateless path).
        from fluxrules.api.engines import APIEngineAdapter

        adapter = APIEngineAdapter(engine_type="PHREAK", db=None, enable_cache=False)

        streaming_engine = PhreakEngine(streaming_mode=True)
        streaming_engine.load_rules([_leaf(1)])

        with caplog.at_level(logging.WARNING):
            adapter._warn_if_streaming_misuse(streaming_engine)
            adapter._warn_if_streaming_misuse(streaming_engine)
            adapter._warn_if_streaming_misuse(streaming_engine)

        warnings = [
            r.getMessage()
            for r in caplog.records
            if r.levelno == logging.WARNING and "streaming-mode engine" in r.getMessage()
        ]
        assert len(warnings) == 1  # one-time, not per call

    def test_no_warning_for_stateless_engine(self, caplog):
        from fluxrules.api.engines import APIEngineAdapter

        adapter = APIEngineAdapter(engine_type="PHREAK", db=None, enable_cache=False)
        stateless_engine = PhreakEngine(streaming_mode=False)
        stateless_engine.load_rules([_leaf(1)])

        with caplog.at_level(logging.WARNING):
            adapter._warn_if_streaming_misuse(stateless_engine)

        warnings = [
            r.getMessage() for r in caplog.records if "streaming-mode engine" in r.getMessage()
        ]
        assert warnings == []


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
