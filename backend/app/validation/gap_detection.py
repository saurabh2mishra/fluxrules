from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Tuple

from app.compiler.rule_compiler import CompiledRule
from app.validation._normalization import intervals_by_field, merge_intervals, NEG_INF, POS_INF


@dataclass
class GapReport:
    field: str
    uncovered_ranges: List[Tuple[float, float]]


class GapDetector:
    def detect(self, compiled_rules: List[CompiledRule]) -> List[GapReport]:
        per_field: Dict[str, list] = {}
        for rule in compiled_rules:
            field_intervals = intervals_by_field(rule)
            for field, intervals in field_intervals.items():
                per_field.setdefault(field, []).extend(intervals)

        reports: List[GapReport] = []
        for field, intervals in per_field.items():
            merged = merge_intervals(intervals)
            gaps: List[Tuple[float, float]] = []
            cursor = NEG_INF
            for interval in merged:
                if interval.low > cursor:
                    gaps.append((cursor, interval.low))
                cursor = max(cursor, interval.high)
            if cursor < POS_INF:
                gaps.append((cursor, POS_INF))
            reports.append(GapReport(field=field, uncovered_ranges=gaps))
        return reports
