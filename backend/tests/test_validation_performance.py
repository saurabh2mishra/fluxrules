import time
import pytest
from app.compiler.rule_compiler import RuleCompiler
from app.validation.conflict_detection import ConflictDetector
from app.validation.redundancy_detection import RedundancyDetector
from app.validation.dead_rule_detection import DeadRuleDetector
from app.validation.coverage_analysis import CoverageAnalyzer
from app.validation.sat_validation import SATValidator
from app.validation.gap_detection import GapDetector
from app.validation.duplicate_detection import DuplicateDetector
from app.validation.priority_collision_detection import PriorityCollisionDetector


def generate_rules(n):
    rules = []
    for i in range(n):
        rules.append({
            "id": f"r{i}",
            "name": f"rule_{i}",
            "priority": i % 100,
            "group": f"g{i % 10}",
            "condition_dsl": {
                "type": "condition",
                "field": f"field_{i % 5}",
                "op": ">=",
                "value": i % 1000
            },
            "action": f"segment={i % 20}"
        })
    return rules


def test_validation_performance_stress():
    N = 10000
    rules = generate_rules(N)
    compiler = RuleCompiler()
    compiled = compiler.compile_rules(rules)

    # Time each detector
    detectors = [
        ("conflict", ConflictDetector().detect),
        ("redundancy", RedundancyDetector().detect),
        ("dead", DeadRuleDetector().detect),
        ("coverage", lambda r: CoverageAnalyzer().analyze(r)),
        ("sat", SATValidator().validate),
        ("gap", GapDetector().detect),
        ("duplicate", DuplicateDetector().detect),
        ("priority_collision", PriorityCollisionDetector().detect),
    ]
    max_seconds = 30  
    for name, detector in detectors:
        start = time.time()
        result = detector(compiled)
        elapsed = time.time() - start
        print(f"{name} detector: {elapsed:.2f}s, result count: {len(result) if hasattr(result, '__len__') else 'n/a'}")
        assert elapsed < max_seconds, f"{name} detector took too long: {elapsed:.2f}s"
