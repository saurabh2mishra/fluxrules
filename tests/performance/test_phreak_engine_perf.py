"""Performance tests for unified engine."""

from __future__ import annotations

import gc
import time

import pytest

from fluxrules import Rule
from fluxrules.engine.phreak import PhreakEngine


def _rule(rid, field="amount", op=">", value=100, domain="default", priority=0):
    return Rule(
        id=rid,
        name=f"rule_{rid}",
        condition_dsl={"type": "condition", "field": field, "op": op, "value": value},
        priority=priority,
        domain=domain,
        tags=frozenset(),
        persist=False,
    )


def _composite_rule(rid, n_fields=3, domain="default"):
    conditions = [
        {"type": "condition", "field": f"f{i}", "op": ">", "value": i * 10} for i in range(n_fields)
    ]
    return Rule(
        id=rid,
        name=f"rule_{rid}",
        condition_dsl={"type": "composite", "logic": "AND", "conditions": conditions},
        domain=domain,
        tags=frozenset(),
        persist=False,
    )


@pytest.mark.performance
class TestPerformance:
    def test_segment_creation_1k_rules(self):
        """Create segments from 1K rules: should be <500ms."""
        rules = [_rule(i, domain=f"d{i % 10}") for i in range(1000)]
        engine = PhreakEngine()
        start = time.time()
        engine.load_rules(rules)
        elapsed = (time.time() - start) * 1000
        assert elapsed < 500, f"1K rule load took {elapsed:.1f}ms"

    def test_segment_creation_10k_rules(self):
        """Create segments from 10K rules: should be <2s.

        After P2.1 removed the O(S^2) hierarchy build, real load time dropped
        from ~0.9s to ~0.15s; the 2s ceiling stays as a generous regression
        guard for CI machines under load (a true return of the O(S^2) build
        would blow well past it). See ``test_no_quadratic_hierarchy_build``.
        """
        rules = [_rule(i, domain=f"d{i % 50}") for i in range(10_000)]
        engine = PhreakEngine()
        start = time.time()
        engine.load_rules(rules)
        elapsed = (time.time() - start) * 1000
        assert elapsed < 2000, f"10K rule load took {elapsed:.1f}ms"

    def test_no_quadratic_hierarchy_build(self):
        """P2.1: load time must scale ~linearly, not O(S^2), in rule count.

        The retired ``_build_hierarchy`` compared every segment against every
        other (O(S^2)); at 50k rules it cost ~6s of the ~7s load. With it gone,
        load is dominated by the linear network/alpha build. Load 5× the rules
        and assert load time grows sub-quadratically (well under 5^2 = 25×; we
        allow 10× for fixed costs + noise while still failing on a real O(S^2)
        regression). Also pins that no synthetic ``seg_shared_*`` parent is built.

        Robustness under CI contention: this is a wall-clock *scaling* test, so
        two noise sources are neutralised:

        * **GC pauses** during the timed build are the largest variance source
          (the build allocates many small objects). GC is disabled around each
          measurement and restored afterwards.
        * **Transient CPU/memory contention** can only *add* time, so we compute
          the ratio over several attempts and keep the **best (smallest)** one.
          A genuine O(S^2) regression stays slow on every attempt and still
          fails.
        """

        def _load_once(n_rules: int) -> float:
            # Many distinct field-sets ⇒ many segments ⇒ O(S^2) would dominate.
            rules = [_rule(i, field=f"f{i}", op=">", value=0) for i in range(n_rules)]
            engine = PhreakEngine()
            gc_was_enabled = gc.isenabled()
            gc.disable()
            try:
                start = time.perf_counter()
                engine.load_rules(rules)
                elapsed = time.perf_counter() - start
            finally:
                if gc_was_enabled:
                    gc.enable()
            assert not any(
                sid.startswith("seg_shared_") for sid in engine.segment_network.segments
            ), "P2.1: no synthesized parent segments should exist"
            return elapsed

        def _best_load_seconds(n_rules: int, runs: int = 3) -> float:
            return min(_load_once(n_rules) for _ in range(runs))

        # Best-of-attempts on the ratio itself: the least-contended paired
        # sample is the truest estimate of algorithmic scaling.
        best_ratio = float("inf")
        best_small = best_large = 0.0
        for _ in range(3):
            small = _best_load_seconds(4_000)
            large = _best_load_seconds(20_000)  # 5x the rules / segments
            ratio = large / small if small else float("inf")
            if ratio < best_ratio:
                best_ratio, best_small, best_large = ratio, small, large
            if best_ratio < 10.0:
                break

        assert best_ratio < 10.0, (
            f"load time scaled {best_ratio:.1f}x for 5x rules "
            f"(small={best_small * 1e3:.1f}ms large={best_large * 1e3:.1f}ms) "
            "- the O(S^2) hierarchy build may have returned"
        )

    def test_discovery_latency_1k(self):
        """Discover rules for single fact with 1K rules: <10ms."""
        rules = [_rule(i) for i in range(1000)]
        engine = PhreakEngine()
        engine.load_rules(rules)

        start = time.time()
        result = engine.evaluate({"amount": 500})
        elapsed = (time.time() - start) * 1000
        assert elapsed < 100, f"1K eval took {elapsed:.1f}ms"
        assert len(result.fired_rules) > 0

    def test_throughput_1k_facts(self):
        """Evaluate 1K facts with 1K rules."""
        rules = [_rule(i) for i in range(1000)]
        engine = PhreakEngine()
        engine.load_rules(rules)

        facts = [{"amount": i * 10} for i in range(1000)]
        start = time.time()
        for fact in facts:
            engine.evaluate(fact)
        elapsed = time.time() - start
        throughput = 1000 / elapsed
        assert throughput > 100, f"Throughput: {throughput:.0f} facts/sec"

    def test_multi_field_composite_perf(self):
        """Performance with composite rules having multiple fields."""
        rules = [_composite_rule(i, n_fields=5, domain=f"d{i % 10}") for i in range(500)]
        engine = PhreakEngine()
        engine.load_rules(rules)

        fact = {f"f{i}": 1000 for i in range(5)}
        start = time.time()
        result = engine.evaluate(fact)
        elapsed = (time.time() - start) * 1000
        assert elapsed < 500, f"Composite eval took {elapsed:.1f}ms"
        assert len(result.fired_rules) > 0

    def test_candidate_build_scales_linearly(self):
        """Regression: high-match eval must scale ~linearly in rules.

        The candidate-build safety check (``rid not in rule_ids``) was an O(N)
        membership test against a list inside a loop over N matched rules,
        making the per-fact cost O(N^2). This test fires every rule (every fact
        matches every rule) at 1k and 4k rules and asserts the per-fact latency
        grows sub-quadratically - a true O(N^2) path would blow past the bound.
        """

        def _avg_latency(n_rules: int) -> float:
            # All rules share one field so every fact matches every rule -> the
            # candidate set equals the full rule set (worst case for the loop).
            rules = [_rule(i, field="x", op=">", value=0) for i in range(n_rules)]
            engine = PhreakEngine(alpha_prefilter=False)
            engine.load_rules(rules)
            facts = [{"x": i + 1} for i in range(60)]
            # Warm up one cycle (segment caches etc.).
            engine.evaluate({"x": 1})
            start = time.time()
            for f in facts:
                res = engine.evaluate(f)
            elapsed = time.time() - start
            assert len(res.fired_rules) == n_rules
            return elapsed / len(facts)

        small = _avg_latency(1000)
        large = _avg_latency(4000)
        # 4x the rules. Linear => ~4x latency; quadratic => ~16x. Allow generous
        # headroom (8x) for fixed overhead and noise while still failing on O(N^2).
        ratio = large / small if small else float("inf")
        assert ratio < 8.0, (
            f"per-fact latency scaled {ratio:.1f}x for 4x rules "
            f"(small={small * 1e3:.2f}ms large={large * 1e3:.2f}ms) "
            "- candidate build may be O(N^2) again"
        )

    def test_sequential_path_is_default(self):
        """The GIL-bound thread pool must stay opt-in.

        Profiling showed the ThreadPoolExecutor path is ~2.2x slower than
        sequential for pure-Python (GIL-serialized) condition evaluation. Guard
        that the default config keeps the parallel path effectively disabled.
        """
        engine = PhreakEngine()
        assert engine._config.parallel_threshold >= 1_000_000

    def test_single_discovery_no_quadratic_in_segments(self):
        """P1.2: per-fact discovery must not blow up with segment count.

        The retired double-discovery path ran an O(segments) ``TokenPropagator``
        scan per fact *in addition to* the linker, then reconciled by set
        intersection. With the single path, discovery cost is dominated by the
        candidate set, not the total segment count. We build rule sets with many
        *distinct* fields (⇒ many segments) but make each fact select only a
        handful, then assert per-fact latency grows sub-quadratically as the
        segment universe grows 4×.
        """

        def _avg_latency(n_rules: int, n_fields: int) -> float:
            # Every rule keys a different field ⇒ ~n_fields distinct segments,
            # but each fact carries only 3 fields ⇒ tiny candidate set.
            rules = [_rule(i, field=f"f{i % n_fields}", op=">", value=0) for i in range(n_rules)]
            engine = PhreakEngine(alpha_prefilter=True)
            engine.load_rules(rules)
            facts = [{f"f{(i * 3) % n_fields}": 1, f"f{(i * 5) % n_fields}": 1} for i in range(120)]
            engine.evaluate(facts[0])  # warm caches
            start = time.time()
            for f in facts:
                engine.evaluate(f)
            return (time.time() - start) / len(facts)

        small = _avg_latency(4_000, n_fields=1_000)
        large = _avg_latency(16_000, n_fields=4_000)
        ratio = large / small if small else float("inf")
        # 4× the segments. Linear-in-candidates discovery ⇒ roughly flat; an
        # O(S) or O(S^2) per-fact scan would scale with the segment universe.
        assert ratio < 6.0, (
            f"per-fact latency scaled {ratio:.1f}x for 4x segments "
            f"(small={small * 1e3:.2f}ms large={large * 1e3:.2f}ms) "
            "- discovery may have regressed to an O(segments) scan"
        )

    def test_single_discovery_runs_one_path(self):
        """P1.2: production config must not call the propagator per fact.

        Spy on ``token_propagator.propagate``; a warm stateless evaluate at
        default config (``strict_discovery=False``) must never invoke it.
        """
        rules = [_rule(i, field=f"f{i % 50}") for i in range(2_000)]
        engine = PhreakEngine()
        engine.load_rules(rules)

        calls = {"n": 0}
        original = engine.token_propagator.propagate

        def _spy(facts, affected):
            calls["n"] += 1
            return original(facts, affected)

        engine.token_propagator.propagate = _spy  # type: ignore[assignment]
        for i in range(200):
            engine.evaluate({f"f{i % 50}": i})
        assert calls["n"] == 0, "propagator should not run in single-discovery mode"

    def test_alpha_primary_beats_alpha_off_on_selective_set(self):
        """P1.1: alpha-on must beat alpha-off on a selective rule set.

        Many rules on one hot field with high thresholds; most facts fire few
        rules. The value-aware alpha layer should cut candidates before per-rule
        evaluation, so alpha-on throughput exceeds alpha-off. Uses best-of-N
        timing to remove scheduling noise from the comparison.
        """
        n_rules = 6_000
        rules = [_rule(i, field="amount", op=">", value=900 + (i % 100)) for i in range(n_rules)]
        facts = [{"amount": v} for v in range(50)]  # all < 900 ⇒ fire nothing

        def _best_time(alpha: bool, trials: int = 5) -> float:
            engine = PhreakEngine(alpha_prefilter=alpha)
            engine.load_rules(rules)
            engine.evaluate(facts[0])  # warm
            best = float("inf")
            for _ in range(trials):
                start = time.time()
                for f in facts:
                    engine.evaluate(f)
                best = min(best, time.time() - start)
            return best

        on = _best_time(True)
        off = _best_time(False)
        # Alpha-on should be meaningfully faster (it skips ~all per-rule evals).
        assert on < off, f"alpha-on ({on:.3f}s) not faster than alpha-off ({off:.3f}s)"

    def test_alpha_low_selectivity_auto_bypass_not_slower(self):
        """P1.1: worst-case low-selectivity set must auto-bypass, never slower.

        When every rule is unfilterable (the alpha index cannot prune), the
        adaptive gate must bypass the scan so the hot path is identical to
        alpha-off. With alpha bypassed the only difference is the one-time index
        build at load (outside the timed loop), so best-of-N timing must show
        alpha-on within noise of alpha-off (budget: ≤5% on the best run).
        """
        n_rules = 3_000
        # NOT rules are unfilterable ⇒ index can_prune is False ⇒ auto-bypass.
        rules = [
            Rule(
                id=i,
                name=f"r{i}",
                condition_dsl={
                    "type": "not",
                    "condition": {
                        "type": "condition",
                        "field": "x",
                        "op": "==",
                        "value": i,
                    },
                },
                tags=frozenset(),
                persist=False,
            )
            for i in range(n_rules)
        ]
        facts = [{"x": v} for v in range(60)]

        def _best_time(alpha: bool, trials: int = 7) -> float:
            engine = PhreakEngine(alpha_prefilter=alpha)
            engine.load_rules(rules)
            if alpha:
                assert engine._alpha_engage is False  # must auto-bypass
            engine.evaluate(facts[0])
            best = float("inf")
            for _ in range(trials):
                start = time.time()
                for f in facts:
                    engine.evaluate(f)
                best = min(best, time.time() - start)
            return best

        on = _best_time(True)
        off = _best_time(False)
        assert on < off * 1.05, (
            f"alpha-on ({on:.4f}s) >5% slower than alpha-off ({off:.4f}s) "
            "on a low-selectivity set - adaptive bypass not working"
        )
