"""Validation performance stress test (ported from backend)."""

import time

import pytest

from fluxrules.services.compilation.rule_compiler import RuleCompiler
from fluxrules.services.validation.conflict_detection import ConflictDetector
from fluxrules.services.validation.coverage_analysis import CoverageAnalyzer
from fluxrules.services.validation.dead_rule_detection import DeadRuleDetector
from fluxrules.services.validation.duplicate_detection import DuplicateDetector
from fluxrules.services.validation.gap_detection import GapDetector
from fluxrules.services.validation.priority_collision_detection import (
    PriorityCollisionDetector,
)
from fluxrules.services.validation.redundancy_detection import RedundancyDetector
from fluxrules.services.validation.sat_validation import SATValidator


def generate_rules(n):
    return [
        {
            "id": f"r{i}",
            "name": f"rule_{i}",
            "priority": i % 100,
            "group": f"g{i % 10}",
            "condition_dsl": {
                "type": "condition",
                "field": f"field_{i % 5}",
                "op": ">=",
                "value": i % 1000,
            },
            "action": f"segment={i % 20}",
        }
        for i in range(n)
    ]


@pytest.mark.performance
def test_validation_performance_stress():
    N = 10000
    rules = generate_rules(N)
    compiled = RuleCompiler().compile_rules(rules)

    # Per-detector wall-clock ceilings. These are *regression guards* that catch
    # pathological blow-ups (accidental higher-order complexity or hangs), not
    # micro-benchmark targets. Most detectors are near-linear and finish in
    # well under a second at N=10000, so a tight 10s ceiling stays meaningful.
    # `conflict` is the outlier: it is O(n^2) in rule count, so at N=10000 it
    # performs ~1e8 comparisons and was observed at 16-52s across machines. It
    # gets a deliberately generous ceiling so normal machine/CI variance does
    # not flake the gate; algorithmic optimisation of ConflictDetector is
    # tracked separately. The test is marked `performance` so it can be
    # deselected from the deterministic unit gate via `-m "not performance"`.
    FAST_BUDGET_SECONDS = 10
    CONFLICT_BUDGET_SECONDS = 120

    detectors = [
        ("conflict", ConflictDetector().detect, CONFLICT_BUDGET_SECONDS),
        ("redundancy", RedundancyDetector().detect, FAST_BUDGET_SECONDS),
        ("dead", DeadRuleDetector().detect, FAST_BUDGET_SECONDS),
        ("coverage", lambda r: CoverageAnalyzer().analyze(r), FAST_BUDGET_SECONDS),
        ("sat", SATValidator().validate, FAST_BUDGET_SECONDS),
        ("gap", GapDetector().detect, FAST_BUDGET_SECONDS),
        ("duplicate", DuplicateDetector().detect, FAST_BUDGET_SECONDS),
        ("priority_collision", PriorityCollisionDetector().detect, FAST_BUDGET_SECONDS),
    ]
    for name, detector, budget in detectors:
        start = time.time()
        _ = detector(compiled)
        elapsed = time.time() - start
        print(f"{name} detector: {elapsed:.2f}s (budget {budget}s)")
        assert elapsed < budget, f"{name} detector took too long: {elapsed:.2f}s"
