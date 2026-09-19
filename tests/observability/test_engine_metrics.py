"""Operational observability tests (PHREAK P2.4).

A known rule/fact mix must produce the expected candidate counts, alpha prune
ratio, leaf-memo hit rate, node-memory hit rate, linked-rule count, and latency
percentiles within tolerance - and the metrics must be **flag-gated** so the
default path pays no measurable overhead.
"""

from __future__ import annotations

import time

import pytest

from fluxrules import Rule
from fluxrules.engine.infrastructure.engine_metrics import (
    EngineMetrics,
    LatencyReservoir,
)
from fluxrules.engine.phreak._engine import PhreakEngine


def _shared_leaf_rules(n: int) -> list[Rule]:
    """n rules that all share the SAME leaf (field=amount, op=>, value=100).

    Within one evaluation cycle the leaf is evaluated once and reused by the
    other n-1 rules ⇒ the leaf memo should show a high hit rate.
    """
    return [
        Rule(
            id=i,
            name=f"r{i}",
            condition_dsl={
                "type": "condition",
                "field": "amount",
                "op": ">",
                "value": 100,
            },
            tags=frozenset(),
            persist=False,
        )
        for i in range(n)
    ]


def _selective_rules(n: int) -> list[Rule]:
    """n rules on one hot field with staggered high thresholds (selective)."""
    return [
        Rule(
            id=i,
            name=f"r{i}",
            condition_dsl={
                "type": "condition",
                "field": "amount",
                "op": ">",
                "value": 900 + (i % 100),
            },
            tags=frozenset(),
            persist=False,
        )
        for i in range(n)
    ]


class TestLatencyReservoir:
    def test_percentiles_on_known_distribution(self):
        res = LatencyReservoir(window=1000)
        for v in range(1, 101):  # 1..100 ms
            res.record(float(v))
        pcts = res.percentiles()
        assert pcts["p50"] == 50
        assert pcts["p95"] == 95
        assert pcts["p99"] == 99
        assert res.count == 100

    def test_window_bounds_memory(self):
        res = LatencyReservoir(window=10)
        for v in range(100):
            res.record(float(v))
        # Only the last 10 are resident, but count tracks all.
        assert res.count == 100
        assert len(res._samples) == 10

    def test_empty_percentiles_are_zero(self):
        res = LatencyReservoir()
        assert res.percentiles() == {"p50": 0.0, "p95": 0.0, "p99": 0.0}


class TestEngineMetricsUnit:
    def test_leaf_and_linked_and_latency(self):
        m = EngineMetrics()
        m.record_leaf(hit=True)
        m.record_leaf(hit=True)
        m.record_leaf(hit=False)
        m.record_linked(5)
        m.record_linked(7)
        m.record_latency_ms(2.0)
        d = m.as_dict()
        assert d["leaf_memo_hits"] == 2
        assert d["leaf_memo_misses"] == 1
        assert abs(d["leaf_memo_hit_rate"] - 2 / 3) < 1e-9
        assert d["linked_rules_last"] == 7
        assert d["linked_rules_avg"] == 6.0
        assert d["eval_latency_samples"] == 1

    def test_reset(self):
        m = EngineMetrics()
        m.record_leaf(hit=True)
        m.record_linked(3)
        m.record_latency_ms(1.0)
        m.reset()
        d = m.as_dict()
        assert d["leaf_memo_hits"] == 0
        assert d["linked_rules_avg"] == 0.0
        assert d["eval_latency_samples"] == 0


class TestEngineObservability:
    def test_disabled_by_default(self):
        engine = PhreakEngine()
        m = engine.get_observability_metrics()
        assert m["enabled"] is False
        # Alpha + WM signals are still present (cheap, always tracked).
        assert "alpha_prune_ratio" in m
        assert "working_memory_size" in m
        # Flag-gated metrics absent when disabled.
        assert "leaf_memo_hit_rate" not in m

    def test_candidate_counts_and_prune_ratio(self):
        engine = PhreakEngine(alpha_prefilter=True, enable_metrics=True)
        engine.load_rules(_selective_rules(1000))
        # All facts are < 900 ⇒ fire nothing ⇒ alpha prunes ~everything.
        for v in range(200):
            engine.evaluate({"amount": v})
        m = engine.get_observability_metrics()
        assert m["enabled"] is True
        assert m["mode"] == "stateless"
        # 1000 candidates in per fact; almost all pruned out.
        assert m["candidates_per_fact_in"] == pytest.approx(1000.0, rel=0.01)
        assert m["candidates_per_fact_out"] < 50
        assert m["alpha_prune_ratio"] > 0.9
        # Latency percentiles populated.
        assert m["eval_latency_samples"] == 200
        assert m["eval_latency_ms_p50"] >= 0.0

    def test_leaf_memo_hit_rate_high_on_shared_leaves(self):
        engine = PhreakEngine(alpha_prefilter=False, enable_metrics=True)
        engine.load_rules(_shared_leaf_rules(50))
        # Every fact > 100 ⇒ all 50 rules are candidates and share one leaf.
        for _ in range(20):
            engine.evaluate({"amount": 500})
        m = engine.get_observability_metrics()
        # 50 rules, 1 distinct leaf per cycle ⇒ ~49/50 hits per cycle.
        assert m["leaf_memo_hit_rate"] > 0.9
        assert m["linked_rules_last"] == 50

    def test_streaming_exposes_node_memory(self):
        engine = PhreakEngine(streaming_mode=True, enable_metrics=True)
        engine.load_rules(_shared_leaf_rules(10))
        engine.evaluate({"amount": 500})
        engine.evaluate({"amount": 500})  # repeat ⇒ node-memory hits
        m = engine.get_observability_metrics()
        assert m["node_memory"] is not None
        assert "hit_rate" in m["node_memory"]
        assert "evictions" in m["node_memory"]

    def test_working_memory_size_tracked(self):
        engine = PhreakEngine(enable_metrics=True)
        engine.load_rules(_shared_leaf_rules(5))
        m = engine.get_observability_metrics()
        assert m["working_memory_size"] == 0  # pure stateless scoring


class TestMetricsOverhead:
    """Metrics-on vs metrics-off latency delta must stay within a budget."""

    def test_overhead_within_budget(self):
        rules = _selective_rules(2000)
        facts = [{"amount": v} for v in range(300)]

        def _best_time(enable: bool, trials: int = 5) -> float:
            engine = PhreakEngine(alpha_prefilter=True, enable_metrics=enable)
            engine.load_rules(rules)
            engine.evaluate(facts[0])  # warm
            best = float("inf")
            for _ in range(trials):
                start = time.perf_counter()
                for f in facts:
                    engine.evaluate(f)
                best = min(best, time.perf_counter() - start)
            return best

        off = _best_time(False)
        on = _best_time(True)
        # Generous budget: metrics are increment-only + a bounded reservoir.
        # On a selective set almost everything is pruned so few leaf records
        # fire; the dominant cost (one latency record + one linked record per
        # fact) is tiny. Allow 25% on best-of-N to absorb scheduling noise.
        assert on < off * 1.25, (
            f"metrics overhead too high: on={on:.4f}s off={off:.4f}s "
            f"({(on / off - 1) * 100:.0f}% over budget)"
        )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
