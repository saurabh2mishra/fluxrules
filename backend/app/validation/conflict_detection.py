from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Tuple

from app.compiler.rule_compiler import CompiledRule
from app.validation._normalization import Interval, intervals_by_field


@dataclass
class RuleConflict:
    left_rule_id: str
    right_rule_id: str
    overlapping_fields: Tuple[str, ...]


class ConflictDetector:
    """Detect rule overlaps using pairwise interval comparison for inclusivity correctness."""

    def detect(self, compiled_rules: List[CompiledRule]) -> List[RuleConflict]:
        rule_intervals: Dict[str, Dict[str, List[Interval]]] = {}
        for rule in compiled_rules:
            field_ranges = intervals_by_field(rule)
            rule_intervals[rule.id] = field_ranges

        pair_to_fields: Dict[tuple[str, str], set[str]] = {}
        rule_ids = list(rule_intervals.keys())
        for i, left_id in enumerate(rule_ids):
            for right_id in rule_ids[i+1:]:
                left_fields = rule_intervals[left_id]
                right_fields = rule_intervals[right_id]
                common_fields = set(left_fields.keys()) & set(right_fields.keys())
                for field in common_fields:
                    for interval1 in left_fields[field]:
                        for interval2 in right_fields[field]:
                            if interval1.intersects(interval2):
                                pair_to_fields.setdefault((left_id, right_id), set()).add(field)
        return [
            RuleConflict(left_rule_id=l, right_rule_id=r, overlapping_fields=tuple(sorted(fields)))
            for (l, r), fields in pair_to_fields.items()
        ]
