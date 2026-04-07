import math

from app.compiler.rule_compiler import RuleCompiler
from app.services.brms_service import BRMSService
from app.validation.conflict_detection import ConflictDetector
from app.validation.dead_rule_detection import DeadRuleDetector
from app.validation.duplicate_detection import DuplicateDetector
from app.validation.gap_detection import GapDetector
from app.validation.redundancy_detection import RedundancyDetector
from app.validation.sat_validation import SATValidator


compiler = RuleCompiler()


def _compile(rules):
    return compiler.compile_rules(rules)


def test_conflict_detector_respects_exclusive_inclusive_boundaries():
    compiled = _compile(
        [
            {
                "id": "r_gt_10",
                "condition_dsl": {"type": "condition", "field": "score", "op": ">", "value": 10},
                "action": "a",
            },
            {
                "id": "r_lte_10",
                "condition_dsl": {"type": "condition", "field": "score", "op": "<=", "value": 10},
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


def test_sat_validator_fallback_excludes_or_rules_from_unsat_claim(monkeypatch):
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
                "condition_dsl": {"type": "condition", "field": "score", "op": "<=", "value": 0},
                "action": "a",
            },
            {
                "id": "gt_zero",
                "condition_dsl": {"type": "condition", "field": "score", "op": ">", "value": 0},
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
                "condition_dsl": {"type": "condition", "field": "score", "op": ">", "value": 100},
                "action": "act1",
            },
            {
                "id": "r2",
                "name": "rule_two",
                "condition_dsl": {"type": "condition", "field": "score", "op": ">", "value": 100},
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
                "condition_dsl": {"type": "condition", "field": "age", "op": ">=", "value": 18},
                "action": "a",
            },
            {
                "id": "child",
                "condition_dsl": {
                    "type": "group",
                    "op": "AND",
                    "children": [
                        {"type": "condition", "field": "age", "op": ">=", "value": 18},
                        {"type": "condition", "field": "score", "op": ">", "value": 100},
                    ],
                },
                "action": "b",
            },
        ]
    )

    redundant = RedundancyDetector().detect(compiled)
    assert not any(r.redundant_rule_id == "child" and r.subsuming_rule_id == "parent" for r in redundant)


def test_brms_service_validate_large_ruleset_returns_complete_report():
    rules = []
    for i in range(250):
        rules.append(
            {
                "id": f"rule_{i}",
                "name": f"rule_{i}",
                "priority": i,
                "group": "scale",
                "condition_dsl": {"type": "condition", "field": "amount", "op": ">", "value": i},
                "action": "notify",
            }
        )

    report = BRMSService().validate(rules)

    # Shape checks for robustness/scalability path
    assert set(report.keys()) == {
        "conflicts",
        "duplicates",
        "priority_collisions",
        "redundancies",
        "dead_rules",
        "gaps",
        "sat",
    }
    assert isinstance(report["conflicts"], list)
    assert isinstance(report["duplicates"], list)
    assert isinstance(report["priority_collisions"], list)
    assert isinstance(report["redundancies"], list)
    assert isinstance(report["dead_rules"], list)
    assert isinstance(report["gaps"], list)
    assert report["sat"]["solver"] in {"fallback", "pysat"}
