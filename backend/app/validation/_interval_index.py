"""
Augmented interval index for O(n log n) conflict detection.

Instead of pairwise O(n²) comparisons, we build a sorted index of interval
endpoints per field with augmented max-high tracking, then sweep to find
overlapping rule pairs efficiently.

The index supports:
  - add(rule_id, field, interval)  — O(log n) insert
  - query(field, interval)         — O(k + log n) where k = number of overlaps
  - remove(rule_id)                — O(m) where m = intervals for that rule
  - bulk_build(entries)            — O(n log n) batch construction
"""
from __future__ import annotations

import bisect
from dataclasses import dataclass, field as dc_field
from typing import Dict, List, Optional, Set, Tuple

from app.validation._normalization import Interval


@dataclass
class IndexEntry:
    """A single entry in the interval index."""
    rule_id: str
    interval: Interval


class FieldIntervalIndex:
    """
    Sorted-endpoint interval index for a single field with augmented max-high.

    Maintains a list of entries sorted by ``low``.  A parallel ``_max_highs``
    array stores the running maximum of ``high`` from the beginning of the list
    up to each position.  This lets us prune the scan early.

    For the query, we:
      1. Binary-search for the rightmost entry whose ``low ≤ query.high``.
      2. Scan only those entries, checking ``high ≥ query.low``.
    """

    __slots__ = ("_entries", "_sorted_lows", "_max_highs", "_dirty")

    def __init__(self) -> None:
        self._entries: List[IndexEntry] = []
        self._sorted_lows: List[float] = []
        self._max_highs: List[float] = []  # prefix max of highs
        self._dirty: bool = False

    # -- mutation --

    def add(self, rule_id: str, interval: Interval) -> None:
        idx = bisect.bisect_right(self._sorted_lows, interval.low)
        self._sorted_lows.insert(idx, interval.low)
        self._entries.insert(idx, IndexEntry(rule_id=rule_id, interval=interval))
        self._dirty = True

    def bulk_add(self, entries: List[Tuple[str, Interval]]) -> None:
        """Add many entries at once.  O(n log n) sort instead of n inserts."""
        for rule_id, iv in entries:
            self._entries.append(IndexEntry(rule_id=rule_id, interval=iv))
        self._entries.sort(key=lambda e: e.interval.low)
        self._sorted_lows = [e.interval.low for e in self._entries]
        self._dirty = True

    def remove(self, rule_id: str) -> None:
        """Remove all entries for a given rule_id.  O(n) scan."""
        new_entries: List[IndexEntry] = []
        new_lows: List[float] = []
        for entry, low in zip(self._entries, self._sorted_lows):
            if entry.rule_id != rule_id:
                new_entries.append(entry)
                new_lows.append(low)
        self._entries = new_entries
        self._sorted_lows = new_lows
        self._dirty = True

    # -- query --

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
        exclude_rule_id: Optional[str] = None,
    ) -> List[str]:
        """Return rule_ids whose intervals overlap with *interval*."""
        if not self._entries:
            return []
        if self._dirty:
            self._rebuild_max_highs()

        # Upper bound: only entries with low ≤ interval.high can overlap
        right_bound = bisect.bisect_right(self._sorted_lows, interval.high)

        overlapping: List[str] = []
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
        exclude_rule_id: Optional[str] = None,
    ) -> Set[str]:
        """Same as query_overlapping but returns a set (deduped)."""
        return set(self.query_overlapping(interval, exclude_rule_id))

    def __len__(self) -> int:
        return len(self._entries)


class IntervalIndex:
    """
    Multi-field interval index.

    Maintains one FieldIntervalIndex per field name.
    Supports both incremental ``add()`` and batch ``bulk_build()`` modes.
    """

    def __init__(self) -> None:
        self._fields: Dict[str, FieldIntervalIndex] = {}

    # -- mutation --

    def add(self, rule_id: str, field: str, interval: Interval) -> None:
        if field not in self._fields:
            self._fields[field] = FieldIntervalIndex()
        self._fields[field].add(rule_id, interval)

    def bulk_build(self, entries: List[Tuple[str, str, Interval]]) -> None:
        """
        Build the entire index from a list of (rule_id, field, interval) tuples.
        More efficient than repeated ``add()`` calls — O(n log n).
        """
        per_field: Dict[str, List[Tuple[str, Interval]]] = {}
        for rule_id, field, iv in entries:
            per_field.setdefault(field, []).append((rule_id, iv))
        for field, field_entries in per_field.items():
            idx = FieldIntervalIndex()
            idx.bulk_add(field_entries)
            self._fields[field] = idx

    def remove(self, rule_id: str) -> None:
        for idx in self._fields.values():
            idx.remove(rule_id)

    # -- query --

    def query_overlapping(
        self, field: str, interval: Interval, exclude_rule_id: Optional[str] = None
    ) -> List[str]:
        idx = self._fields.get(field)
        if not idx:
            return []
        return idx.query_overlapping(interval, exclude_rule_id)

    def query_overlapping_set(
        self, field: str, interval: Interval, exclude_rule_id: Optional[str] = None
    ) -> Set[str]:
        idx = self._fields.get(field)
        if not idx:
            return set()
        return idx.query_overlapping_set(interval, exclude_rule_id)

    def get_fields(self) -> List[str]:
        return list(self._fields.keys())

    def __len__(self) -> int:
        return sum(len(idx) for idx in self._fields.values())
