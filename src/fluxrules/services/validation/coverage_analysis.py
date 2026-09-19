from __future__ import annotations

from dataclasses import dataclass

from fluxrules.services.compilation.rule_compiler import CompiledRule
from fluxrules.services.validation._normalization import (
    NEG_INF,
    POS_INF,
    Interval,
    intervals_by_field,
    merge_intervals,
)


@dataclass
class CoverageReport:
    total_rules: int
    triggered_rules: int
    uncovered_ranges: dict[str, list[tuple[float, float]]]


class CoverageAnalyzer:
    def analyze(
        self,
        compiled_rules: list[CompiledRule],
        triggered_rule_ids: set[str] | None = None,
    ) -> CoverageReport:
        per_field: dict[str, list[Interval]] = {}
        for rule in compiled_rules:
            for field, ranges in intervals_by_field(rule).items():
                per_field.setdefault(field, []).extend(ranges)

        uncovered: dict[str, list[tuple[float, float]]] = {}
        for field, ranges in per_field.items():
            merged = merge_intervals(ranges)
            uncovered[field] = self._compute_gaps(merged)

        return CoverageReport(
            total_rules=len(compiled_rules),
            triggered_rules=len(triggered_rule_ids or set()),
            uncovered_ranges=uncovered,
        )

    def _compute_gaps(self, ranges: list[Interval]) -> list[tuple[float, float]]:
        if not ranges:
            return [(NEG_INF, POS_INF)]
        gaps: list[tuple[float, float]] = []
        cursor = NEG_INF
        for interval in ranges:
            if interval.low > cursor:
                gaps.append((cursor, interval.low))
            cursor = max(cursor, interval.high)
        if cursor < POS_INF:
            gaps.append((cursor, POS_INF))
        return gaps
