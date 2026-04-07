from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Tuple

from app.compiler.rule_compiler import CompiledRule
from app.validation._normalization import Interval, intervals_by_field, merge_intervals, NEG_INF, POS_INF


@dataclass
class CoverageReport:
    total_rules: int
    triggered_rules: int
    uncovered_ranges: Dict[str, List[Tuple[float, float]]]


class CoverageAnalyzer:
    def analyze(self, compiled_rules: List[CompiledRule], triggered_rule_ids: set[str] | None = None) -> CoverageReport:
        per_field: Dict[str, List[Interval]] = {}
        for rule in compiled_rules:
            for field, ranges in intervals_by_field(rule).items():
                per_field.setdefault(field, []).extend(ranges)

        uncovered: Dict[str, List[Tuple[float, float]]] = {}
        for field, ranges in per_field.items():
            merged = merge_intervals(ranges)
            uncovered[field] = self._compute_gaps(merged)

        return CoverageReport(
            total_rules=len(compiled_rules),
            triggered_rules=len(triggered_rule_ids or set()),
            uncovered_ranges=uncovered,
        )

    def _compute_gaps(self, ranges: List[Interval]) -> List[Tuple[float, float]]:
        if not ranges:
            return [(NEG_INF, POS_INF)]
        gaps: List[Tuple[float, float]] = []
        cursor = NEG_INF
        for interval in ranges:
            if interval.low > cursor:
                gaps.append((cursor, interval.low))
            cursor = max(cursor, interval.high)
        if cursor < POS_INF:
            gaps.append((cursor, POS_INF))
        return gaps
