from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, List, Optional

from app.compiler.rule_compiler import CompiledConstraint, CompiledRule


NEG_INF = float("-inf")
POS_INF = float("inf")


@dataclass(frozen=True)
class Interval:
    low: float
    high: float
    low_inclusive: bool = False
    high_inclusive: bool = False

    def intersects(self, other: "Interval") -> bool:
        if self.high < other.low or other.high < self.low:
            return False
        if self.high == other.low:
            return self.high_inclusive and other.low_inclusive
        if other.high == self.low:
            return other.high_inclusive and self.low_inclusive
        return True

    def intersection(self, other: "Interval") -> Optional["Interval"]:
        if not self.intersects(other):
            return None
        low = max(self.low, other.low)
        high = min(self.high, other.high)

        low_inclusive = self.low_inclusive if self.low >= other.low else other.low_inclusive
        if self.low == other.low:
            low_inclusive = self.low_inclusive and other.low_inclusive

        high_inclusive = self.high_inclusive if self.high <= other.high else other.high_inclusive
        if self.high == other.high:
            high_inclusive = self.high_inclusive and other.high_inclusive
        return Interval(low=low, high=high, low_inclusive=low_inclusive, high_inclusive=high_inclusive)

    def contains(self, other: "Interval") -> bool:
        left_ok = self.low < other.low or (self.low == other.low and (self.low_inclusive or not other.low_inclusive))
        right_ok = self.high > other.high or (self.high == other.high and (self.high_inclusive or not other.high_inclusive))
        return left_ok and right_ok


def constraint_to_interval(constraint: CompiledConstraint) -> Optional[Interval]:
    v = constraint.value
    if not isinstance(v, (int, float)):
        return None

    op = constraint.operator
    if op == ">":
        return Interval(low=float(v), high=POS_INF, low_inclusive=False, high_inclusive=False)
    if op == ">=":
        return Interval(low=float(v), high=POS_INF, low_inclusive=True, high_inclusive=False)
    if op == "<":
        return Interval(low=NEG_INF, high=float(v), low_inclusive=False, high_inclusive=False)
    if op == "<=":
        return Interval(low=NEG_INF, high=float(v), low_inclusive=False, high_inclusive=True)
    if op == "==":
        return Interval(low=float(v), high=float(v), low_inclusive=True, high_inclusive=True)
    return None


def merge_intervals(intervals: Iterable[Interval]) -> List[Interval]:
    ordered = sorted(intervals, key=lambda x: (x.low, x.high))
    if not ordered:
        return []

    merged = [ordered[0]]
    for nxt in ordered[1:]:
        cur = merged[-1]
        if cur.intersects(nxt) or cur.high == nxt.low:
            merged[-1] = Interval(
                low=cur.low,
                high=max(cur.high, nxt.high),
                low_inclusive=cur.low_inclusive,
                high_inclusive=cur.high_inclusive if cur.high >= nxt.high else nxt.high_inclusive,
            )
        else:
            merged.append(nxt)
    return merged


def intervals_by_field(rule: CompiledRule) -> dict[str, List[Interval]]:
    result: dict[str, List[Interval]] = {}
    for c in rule.constraints:
        interval = constraint_to_interval(c)
        if interval is None:
            continue
        result.setdefault(c.field, []).append(interval)
    return {field: merge_intervals(parts) for field, parts in result.items()}
