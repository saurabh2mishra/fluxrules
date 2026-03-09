import pytest
from app.validation.conflict_detection import ConflictDetector, RuleConflict
from app.validation._normalization import Interval
from app.compiler.rule_compiler import CompiledRule

class DummyCompiledRule:
    def __init__(self, id, name, field_ranges, group="default"):
        self.id = id
        self.name = name
        self.source_condition = {}
        self.constraints = []
        self._field_ranges = field_ranges
        self.group = group

from app.validation._normalization import intervals_by_field as _original_intervals_by_field

def intervals_by_field(rule):
    # Patch for DummyCompiledRule in tests
    if hasattr(rule, '_field_ranges'):
        inclusive_ranges = {}
        for field, intervals in rule._field_ranges.items():
            inclusive_ranges[field] = [
                Interval(i.low, i.high, low_inclusive=True, high_inclusive=True)
                for i in intervals
            ]
        return inclusive_ranges
    return _original_intervals_by_field(rule)

# Replace the import globally
import sys
sys.modules['app.validation.conflict_detection'].intervals_by_field = intervals_by_field

@pytest.mark.parametrize("rules,expected", [
    # No overlap
    ([
        DummyCompiledRule("1", "Rule1", {"score": [Interval(0, 10, True, True)]}),
        DummyCompiledRule("2", "Rule2", {"score": [Interval(20, 30, True, True)]}),
    ], []),
    # Overlap (adjacent inclusive intervals)
    ([
        DummyCompiledRule("1", "Rule1", {"score": [Interval(0, 15, True, True)]}),
        DummyCompiledRule("2", "Rule2", {"score": [Interval(14, 20, True, True)]}),
    ], [RuleConflict(left_rule_id="1", right_rule_id="2", overlapping_fields=("score",))]),
    # Multiple fields (guaranteed overlap for both fields)
    ([
        DummyCompiledRule("1", "Rule1", {"score": [Interval(0, 15, True, True)], "age": [Interval(25, 30, True, True)]}),
        DummyCompiledRule("2", "Rule2", {"score": [Interval(14, 20, True, True)], "age": [Interval(28, 35, True, True)]}),
    ], [RuleConflict(left_rule_id="1", right_rule_id="2", overlapping_fields=("age", "score"))]),
])
def test_conflict_detector_overlap(rules, expected):
    detector = ConflictDetector()
    result = detector.detect(rules)
    assert len(result) == len(expected)
    for rc in expected:
        assert any(
            r.left_rule_id == rc.left_rule_id and r.right_rule_id == rc.right_rule_id and set(r.overlapping_fields) == set(rc.overlapping_fields)
            for r in result
        )
