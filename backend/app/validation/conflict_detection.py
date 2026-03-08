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
    """Detect rule overlaps using per-field inverted indexes."""

    def detect(self, compiled_rules: List[CompiledRule]) -> List[RuleConflict]:
        indexed: Dict[str, List[tuple[str, Interval]]] = {}
        for rule in compiled_rules:
            field_ranges = intervals_by_field(rule)
            for field, ranges in field_ranges.items():
                bucket = indexed.setdefault(field, [])
                for interval in ranges:
                    bucket.append((rule.id, interval))

        pair_to_fields: Dict[tuple[str, str], set[str]] = {}
        for field, entries in indexed.items():
            entries.sort(key=lambda x: x[1].low)
            active: List[tuple[str, Interval]] = []
            for rid, interval in entries:
                active = [(arid, aint) for arid, aint in active if aint.high >= interval.low]
                for arid, aint in active:
                    if arid == rid or not aint.intersects(interval):
                        continue
                    left, right = sorted((arid, rid))
                    pair_to_fields.setdefault((left, right), set()).add(field)
                active.append((rid, interval))

        return [
            RuleConflict(left_rule_id=l, right_rule_id=r, overlapping_fields=tuple(sorted(fields)))
            for (l, r), fields in pair_to_fields.items()
        ]
