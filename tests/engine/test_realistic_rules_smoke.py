"""P1.3 - CI smoke test for the realistic-rule benchmark.

A fast subset of ``tests/performance/perf_realistic_rules.py`` that runs in
*regular* CI (not gated behind the ``performance`` marker) to catch scaling
regressions early. It reuses the harness's generators + ``measure`` so the CI
gate and the full benchmark can never drift apart.

What it gates (from ``.research/PHREAK_P1_PLAN_SCALING_EFFICIENCY.md`` P1.3):

- p50/p95/p99 per-fact latency are produced and ordered (p50 ≤ p95 ≤ p99).
- A **p95 budget** at a CI-sized scale fails the build on regression.
- The alpha layer actually prunes on a realistic (selective) rule set.
- The adversarial hot-field case is measured and reported as the honest worst
  case (alpha prune ratio is low - we don't *require* a budget there, only that
  it stays sound and is characterized).

The budgets are deliberately generous (CI runners are noisy / shared); their job
is to catch an *order-of-magnitude* regression (e.g. discovery going O(rules²) or
the alpha layer silently disengaging), not to benchmark hardware.
"""

from __future__ import annotations

import random

import pytest
from tests.performance.perf_realistic_rules import (
    WorkloadConfig,
    generate_adversarial_rules,
    generate_facts,
    generate_rules,
    measure,
)

# CI-sized scale: big enough to exercise discovery + alpha, small enough to run
# in a few seconds on a shared runner.
_CI_RULES = 4_000
_CI_FACTS = 300
_SEED = 2024

# Generous p95 budget (ms/fact). Catches an order-of-magnitude regression, not
# hardware noise. At 4k realistic rules a healthy engine is single-digit ms.
_P95_BUDGET_MS = 60.0


@pytest.fixture(scope="module")
def realistic_report():
    cfg = WorkloadConfig()
    rng = random.Random(_SEED)
    rules = generate_rules(_CI_RULES, cfg, rng)
    facts = generate_facts(_CI_FACTS, cfg, rng)
    return measure(rules, facts, alpha=True)


def test_percentiles_are_produced_and_ordered(realistic_report):
    rep = realistic_report
    assert rep.p50_ms > 0.0
    assert rep.p50_ms <= rep.p95_ms <= rep.p99_ms
    assert rep.throughput_fps > 0.0


def test_p95_within_budget(realistic_report):
    rep = realistic_report
    assert rep.p95_ms < _P95_BUDGET_MS, (
        f"p95 {rep.p95_ms:.2f}ms exceeds CI budget {_P95_BUDGET_MS}ms at "
        f"{_CI_RULES} realistic rules - possible scaling regression"
    )


def test_alpha_prunes_on_realistic_rules(realistic_report):
    pf = realistic_report.prefilter
    assert pf["enabled"] is True
    assert pf["engaged"] is True
    # Realistic selective rules ⇒ the value-aware alpha layer should drop a
    # meaningful fraction of candidates before per-rule evaluation.
    assert pf["prune_ratio"] > 0.10, (
        f"alpha prune ratio {pf['prune_ratio']:.2%} unexpectedly low - the "
        "primary reducer may have regressed"
    )


def test_adversarial_hot_field_is_sound_and_characterized():
    """The honest worst case: alpha can't prune, but results stay correct.

    We don't gate latency here (it's intentionally the bad case); we assert the
    harness measures it and that fired facts are still produced soundly (every
    adversarial fact carries the hot field passing the loose threshold ⇒ fires).
    """
    cfg = WorkloadConfig()
    rng = random.Random(_SEED)
    rules = generate_adversarial_rules(_CI_RULES, cfg, rng)
    facts = generate_facts(_CI_FACTS, cfg, rng, adversarial=True)
    rep = measure(rules, facts, alpha=True)

    assert rep.p50_ms <= rep.p95_ms <= rep.p99_ms
    # Hot field passes ⇒ the ~90% hot rules fire on every fact.
    assert rep.fired_facts == _CI_FACTS
    # Alpha is engaged (the index *can* prune the minority non-hot rules) but the
    # ratio is low because the hot majority is unprunable - the honest signal.
    pf = rep.prefilter
    assert pf["prune_ratio"] < 0.5, (
        "adversarial set should show LOW prune ratio (that's the point); "
        f"got {pf['prune_ratio']:.2%}"
    )


def test_alpha_on_off_fired_parity_on_realistic_set():
    """Soundness still holds on the realistic generator: alpha-on ≡ alpha-off."""
    cfg = WorkloadConfig()
    rng = random.Random(_SEED)
    rules = generate_rules(1_500, cfg, rng)
    facts = generate_facts(400, cfg, rng)

    from fluxrules.engine.phreak import PhreakEngine

    on = PhreakEngine(alpha_prefilter=True)
    on.load_rules(rules)
    off = PhreakEngine(alpha_prefilter=False)
    off.load_rules(rules)
    for f in facts:
        assert set(on.evaluate(f).fired_rules) == set(off.evaluate(f).fired_rules)
