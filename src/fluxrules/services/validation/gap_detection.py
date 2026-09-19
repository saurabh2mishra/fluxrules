from __future__ import annotations

from dataclasses import dataclass

from fluxrules.services.compilation.rule_compiler import CompiledRule
from fluxrules.services.validation._normalization import (
    NEG_INF,
    POS_INF,
    intervals_by_field,
    merge_intervals,
)


@dataclass
class GapReport:
    field: str
    uncovered_ranges: list[tuple[float, float]]


class GapDetector:
    def detect(self, compiled_rules: list[CompiledRule]) -> list[GapReport]:
        per_field: dict[str, list] = {}
        for rule in compiled_rules:
            field_intervals = intervals_by_field(rule)
            for field, intervals in field_intervals.items():
                per_field.setdefault(field, []).extend(intervals)

        reports: list[GapReport] = []
        for field, intervals in per_field.items():
            merged = merge_intervals(intervals)
            gaps: list[tuple[float, float]] = []
            cursor = NEG_INF
            for interval in merged:
                if interval.low > cursor:
                    gaps.append((cursor, interval.low))
                cursor = max(cursor, interval.high)
            if cursor < POS_INF:
                gaps.append((cursor, POS_INF))
            reports.append(GapReport(field=field, uncovered_ranges=gaps))
        return reports
