"""
Augmented interval index for O(n log n) conflict detection.
"""

from __future__ import annotations

import bisect
from dataclasses import dataclass
from typing import Any

from fluxrules.services.validation._normalization import Interval


@dataclass
class IndexEntry:
    """A single entry in the interval index."""

    rule_id: str
    interval: Interval


class FieldIntervalIndex:
    """
    Sorted-endpoint interval index for a single field with augmented max-high.
    """

    __slots__ = ("_dirty", "_entries", "_max_highs", "_sorted_lows")

    def __init__(self) -> None:
        self._entries: list[IndexEntry] = []
        self._sorted_lows: list[float] = []
        self._max_highs: list[float] = []
        self._dirty: bool = False

    def add(self, rule_id: str, interval: Interval) -> None:
        idx = bisect.bisect_right(self._sorted_lows, interval.low)
        self._sorted_lows.insert(idx, interval.low)
        self._entries.insert(idx, IndexEntry(rule_id=rule_id, interval=interval))
        self._dirty = True

    def bulk_add(self, entries: list[tuple[str, Interval]]) -> None:
        for rule_id, iv in entries:
            self._entries.append(IndexEntry(rule_id=rule_id, interval=iv))
        self._entries.sort(key=lambda e: e.interval.low)
        self._sorted_lows = [e.interval.low for e in self._entries]
        self._dirty = True

    def remove(self, rule_id: str) -> None:
        new_entries: list[IndexEntry] = []
        new_lows: list[float] = []
        for entry, low in zip(self._entries, self._sorted_lows):
            if entry.rule_id != rule_id:
                new_entries.append(entry)
                new_lows.append(low)
        self._entries = new_entries
        self._sorted_lows = new_lows
        self._dirty = True

    def _rebuild_max_highs(self) -> None:
        n = len(self._entries)
        if n == 0:
            self._max_highs = []
        else:
            self._max_highs = [0.0] * n
            running = float("-inf")
            for i in range(n):
                running = max(running, self._entries[i].interval.high)
                self._max_highs[i] = running
        self._dirty = False

    def query_overlapping(
        self,
        interval: Interval,
        exclude_rule_id: str | None = None,
    ) -> list[str]:
        if not self._entries:
            return []
        if self._dirty:
            self._rebuild_max_highs()

        right_bound = bisect.bisect_right(self._sorted_lows, interval.high)

        overlapping: list[str] = []
        for i in range(right_bound):
            entry = self._entries[i]
            if exclude_rule_id and entry.rule_id == exclude_rule_id:
                continue
            if entry.interval.intersects(interval):
                overlapping.append(entry.rule_id)
        return overlapping

    def query_overlapping_set(
        self,
        interval: Interval,
        exclude_rule_id: str | None = None,
    ) -> set[str]:
        return set(self.query_overlapping(interval, exclude_rule_id))

    def __len__(self) -> int:
        return len(self._entries)


class IntervalIndex:
    """Multi-field interval index."""

    def __init__(self) -> None:
        self._fields: dict[str, FieldIntervalIndex] = {}

    def add(self, rule_id: str, field: str, interval: Interval) -> None:
        if field not in self._fields:
            self._fields[field] = FieldIntervalIndex()
        self._fields[field].add(rule_id, interval)

    def bulk_build(self, entries: list[tuple[str, str, Interval]]) -> None:
        per_field: dict[str, list[tuple[str, Interval]]] = {}
        for rule_id, field, iv in entries:
            per_field.setdefault(field, []).append((rule_id, iv))
        for field, field_entries in per_field.items():
            idx = FieldIntervalIndex()
            idx.bulk_add(field_entries)
            self._fields[field] = idx

    def remove(self, rule_id: str) -> None:
        for idx in self._fields.values():
            idx.remove(rule_id)

    def query_overlapping(
        self, field: str, interval: Interval, exclude_rule_id: str | None = None
    ) -> list[str]:
        idx = self._fields.get(field)
        if not idx:
            return []
        return idx.query_overlapping(interval, exclude_rule_id)

    def query_overlapping_set(
        self, field: str, interval: Interval, exclude_rule_id: str | None = None
    ) -> set[str]:
        idx = self._fields.get(field)
        if not idx:
            return set()
        return idx.query_overlapping_set(interval, exclude_rule_id)

    def get_fields(self) -> list[str]:
        return list(self._fields.keys())

    def __len__(self) -> int:
        return sum(len(idx) for idx in self._fields.values())


class EqualityIndex:
    """Multi-field hash index for **non-numeric equality** constraints.

    :class:`IntervalIndex` can only index constraints that map to a numeric
    interval. A rule whose conditions are purely string equality
    (``tier == "premium"``) therefore never entered the index, was never
    returned as a candidate, and so could never be reported as conflicting -
    silently. Categorical rulesets are common, and "no conflicts found" is the
    worst possible way to be wrong.

    This index closes that gap. Lookup is by exact value, which is all that
    equality overlap requires: two ``==`` constraints on the same field overlap
    if and only if they share a value.
    """

    def __init__(self) -> None:
        # field -> value -> {rule_id}
        self._fields: dict[str, dict[Any, set[str]]] = {}

    def add(self, rule_id: str, field: str, value: Any) -> None:
        try:
            self._fields.setdefault(field, {}).setdefault(value, set()).add(rule_id)
        except TypeError:
            # Unhashable value (list, dict). Nothing sensible to index, and
            # skipping is safe: it costs a candidate, not a false positive.
            return

    def remove(self, rule_id: str) -> None:
        for by_value in self._fields.values():
            for ids in by_value.values():
                ids.discard(rule_id)

    def query_equal(self, field: str, value: Any, exclude_rule_id: str | None = None) -> set[str]:
        by_value = self._fields.get(field)
        if not by_value:
            return set()
        try:
            hits = by_value.get(value)
        except TypeError:
            return set()
        if not hits:
            return set()
        if exclude_rule_id is None:
            return set(hits)
        return {rid for rid in hits if rid != exclude_rule_id}

    def get_fields(self) -> list[str]:
        return list(self._fields.keys())

    def __len__(self) -> int:
        return sum(len(ids) for by_value in self._fields.values() for ids in by_value.values())
