"""BRMS validation tests"""

import math

from fluxrules.services.compilation.rule_compiler import RuleCompiler
from fluxrules.services.validation.conflict_detection import ConflictDetector
from fluxrules.services.validation.coverage_analysis import CoverageAnalyzer
from fluxrules.services.validation.dead_rule_detection import DeadRuleDetector
from fluxrules.services.validation.duplicate_detection import DuplicateDetector
from fluxrules.services.validation.gap_detection import GapDetector
from fluxrules.services.validation.redundancy_detection import RedundancyDetector
from fluxrules.services.validation.sat_validation import SATValidator

compiler = RuleCompiler()


def _compile(rules):
    return compiler.compile_rules(rules)


def _rules():
    return [
        {
            "id": "r1",
            "name": "adult",
            "priority": 10,
            "condition_dsl": {
                "type": "condition",
                "field": "age",
                "op": ">=",
                "value": 18,
            },
            "action": "segment=adult",
        },
        {
            "id": "r2",
            "name": "senior",
            "priority": 20,
            "condition_dsl": {
                "type": "condition",
                "field": "age",
                "op": ">=",
                "value": 65,
            },
            "action": "segment=senior",
        },
        {
            "id": "r3",
            "name": "impossible",
            "priority": 5,
            "condition_dsl": {
                "type": "group",
                "op": "AND",
                "children": [
                    {"type": "condition", "field": "age", "op": ">", "value": 60},
                    {"type": "condition", "field": "age", "op": "<", "value": 50},
                ],
            },
            "action": "flag=bad",
        },
    ]


#  Core validation tests


def test_coverage_analysis_reports_global_gap():
    compiled = _compile(_rules()[:2])
    report = CoverageAnalyzer().analyze(compiled)
    assert "age" in report.uncovered_ranges
    assert report.total_rules == 2


def test_conflict_detection_finds_overlap():
    compiled = _compile(_rules()[:2])
    conflicts = ConflictDetector().detect(compiled)
    assert any({"r1", "r2"} == {c.left_rule_id, c.right_rule_id} for c in conflicts)


def test_redundancy_detection_finds_subsumed_rule():
    compiled = _compile(_rules()[:2])
    redundant = RedundancyDetector().detect(compiled)
    assert any(r.redundant_rule_id == "r2" and r.subsuming_rule_id == "r1" for r in redundant)


def test_dead_rule_detection_detects_contradiction():
    compiled = _compile(_rules())
    dead = DeadRuleDetector().detect(compiled)
    assert any(d.rule_id == "r3" for d in dead)


def test_sat_validation_works_with_fallback_or_pysat():
    compiled = _compile(_rules())
    result = SATValidator().validate(compiled)
    assert "r3" in result.unsatisfiable_rule_ids
    assert "r2" in result.subsumed_rules
    assert result.solver in {"pysat", "fallback"}


def test_sat_validation_handles_or_groups():
    rules = [
        {
            "id": "or_rule",
            "condition_dsl": {
                "type": "group",
                "op": "OR",
                "children": [
                    {"type": "condition", "field": "age", "op": "<", "value": 10},
                    {"type": "condition", "field": "age", "op": ">", "value": 20},
                ],
            },
            "action": "ok",
        }
    ]
    compiled = _compile(rules)
    result = SATValidator().validate(compiled)
    assert "or_rule" not in result.unsatisfiable_rule_ids


#  Edge cases


def test_conflict_detector_respects_exclusive_inclusive_boundaries():
    compiled = _compile(
        [
            {
                "id": "r_gt_10",
                "condition_dsl": {
                    "type": "condition",
                    "field": "score",
                    "op": ">",
                    "value": 10,
                },
                "action": "a",
            },
            {
                "id": "r_lte_10",
                "condition_dsl": {
                    "type": "condition",
                    "field": "score",
                    "op": "<=",
                    "value": 10,
                },
                "action": "b",
            },
        ]
    )
    conflicts = ConflictDetector().detect(compiled)
    assert conflicts == []


def test_dead_rule_detector_flags_equality_violating_exclusive_bound():
    compiled = _compile(
        [
            {
                "id": "dead_eq_bound",
                "condition_dsl": {
                    "type": "group",
                    "op": "AND",
                    "children": [
                        {"type": "condition", "field": "age", "op": "==", "value": 18},
                        {"type": "condition", "field": "age", "op": ">", "value": 18},
                    ],
                },
                "action": "a",
            }
        ]
    )
    dead = DeadRuleDetector().detect(compiled)
    assert len(dead) == 1
    assert dead[0].rule_id == "dead_eq_bound"
    assert "lower bound" in dead[0].reason


def test_sat_validator_fallback_excludes_or_rules(monkeypatch):
    rules = [
        {
            "id": "or_contradictory_if_flattened",
            "condition_dsl": {
                "type": "group",
                "op": "OR",
                "children": [
                    {"type": "condition", "field": "age", "op": ">", "value": 60},
                    {"type": "condition", "field": "age", "op": "<", "value": 50},
                ],
            },
            "action": "a",
        }
    ]
    compiled = _compile(rules)
    validator = SATValidator()
    monkeypatch.setattr(validator, "_pysat_available", lambda: False)
    result = validator.validate(compiled)
    assert result.solver == "fallback"
    assert result.unsatisfiable_rule_ids == []


def test_gap_detector_has_no_finite_internal_gap_for_complete_split_ranges():
    compiled = _compile(
        [
            {
                "id": "lte_zero",
                "condition_dsl": {
                    "type": "condition",
                    "field": "score",
                    "op": "<=",
                    "value": 0,
                },
                "action": "a",
            },
            {
                "id": "gt_zero",
                "condition_dsl": {
                    "type": "condition",
                    "field": "score",
                    "op": ">",
                    "value": 0,
                },
                "action": "b",
            },
        ]
    )
    gaps = GapDetector().detect(compiled)
    score_gap = next(g for g in gaps if g.field == "score")
    assert all(math.isinf(low) or math.isinf(high) for low, high in score_gap.uncovered_ranges)


def test_duplicate_detector_reports_identical_conditions():
    compiled = _compile(
        [
            {
                "id": "r1",
                "name": "rule_one",
                "condition_dsl": {
                    "type": "condition",
                    "field": "score",
                    "op": ">",
                    "value": 100,
                },
                "action": "act1",
            },
            {
                "id": "r2",
                "name": "rule_two",
                "condition_dsl": {
                    "type": "condition",
                    "field": "score",
                    "op": ">",
                    "value": 100,
                },
                "action": "act2",
            },
        ]
    )
    duplicates = DuplicateDetector().detect(compiled)
    assert len(duplicates) == 1
    assert duplicates[0]["rule1_id"] == "r1"
    assert duplicates[0]["rule2_id"] == "r2"


def test_redundancy_detector_does_not_subsume_when_parent_missing_child_field():
    compiled = _compile(
        [
            {
                "id": "parent",
                "condition_dsl": {
                    "type": "condition",
                    "field": "age",
                    "op": ">=",
                    "value": 18,
                },
                "action": "a",
            },
            {
                "id": "child",
                "condition_dsl": {
                    "type": "group",
                    "op": "AND",
                    "children": [
                        {"type": "condition", "field": "age", "op": ">=", "value": 18},
                        {
                            "type": "condition",
                            "field": "score",
                            "op": ">",
                            "value": 100,
                        },
                    ],
                },
                "action": "b",
            },
        ]
    )
    redundant = RedundancyDetector().detect(compiled)
    assert not any(
        r.redundant_rule_id == "child" and r.subsuming_rule_id == "parent" for r in redundant
    )
