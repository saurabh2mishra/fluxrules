from app.compiler.rule_compiler import RuleCompiler
from app.validation.coverage_analysis import CoverageAnalyzer
from app.validation.conflict_detection import ConflictDetector
from app.validation.redundancy_detection import RedundancyDetector
from app.validation.dead_rule_detection import DeadRuleDetector
from app.validation.sat_validation import SATValidator


def _rules():
    return [
        {
            "id": "r1",
            "name": "adult",
            "priority": 10,
            "condition_dsl": {"type": "condition", "field": "age", "op": ">=", "value": 18},
            "action": "segment=adult",
        },
        {
            "id": "r2",
            "name": "senior",
            "priority": 20,
            "condition_dsl": {"type": "condition", "field": "age", "op": ">=", "value": 65},
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


def test_coverage_analysis_reports_global_gap():
    compiled = RuleCompiler().compile_rules(_rules()[:2])
    report = CoverageAnalyzer().analyze(compiled)
    assert "age" in report.uncovered_ranges
    assert report.total_rules == 2


def test_conflict_detection_finds_overlap():
    compiled = RuleCompiler().compile_rules(_rules()[:2])
    conflicts = ConflictDetector().detect(compiled)
    assert any({"r1", "r2"} == {c.left_rule_id, c.right_rule_id} for c in conflicts)


def test_redundancy_detection_finds_subsumed_rule():
    compiled = RuleCompiler().compile_rules(_rules()[:2])
    redundant = RedundancyDetector().detect(compiled)
    assert any(r.redundant_rule_id == "r2" and r.subsuming_rule_id == "r1" for r in redundant)


def test_dead_rule_detection_detects_contradiction():
    compiled = RuleCompiler().compile_rules(_rules())
    dead = DeadRuleDetector().detect(compiled)
    assert any(d.rule_id == "r3" for d in dead)


def test_sat_validation_works_with_fallback_or_pysat():
    compiled = RuleCompiler().compile_rules(_rules())
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
    compiled = RuleCompiler().compile_rules(rules)
    result = SATValidator().validate(compiled)
    assert "or_rule" not in result.unsatisfiable_rule_ids
