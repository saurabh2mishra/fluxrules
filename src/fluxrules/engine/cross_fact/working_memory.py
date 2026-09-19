"""Typed working memory for the cross-fact engine (stages B-α/B-β).

Unlike the single-fact engine - which is handed one anonymous ``dict`` per
``evaluate`` and holds nothing - the cross-fact engine must **retain** many typed facts
and correlate across them. :class:`CrossFactWorkingMemory` provides:

- **Typed storage** keyed by stable :class:`FactHandle` identity, grouped by
  ``fact_type`` so a pattern can scan only the facts of the type it matches.
- **Equality-join hash indexes** (``fact_type`` + ``field`` -> value -> handles)
  built lazily and maintained incrementally on insert/update/retract, so an
  indexed equality join is O(matching facts) instead of O(all facts of the type)
  - the single most important item for join scale (design note B.2).

Lifecycle (``insert`` / ``update`` / ``retract``) keeps identity stable across
``update`` so the engine's truth maintenance can re-derive matches without
callers re-keying facts.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from itertools import count
from typing import Any

from fluxrules.engine.cross_fact.models import FactHandle


class CrossFactWorkingMemory:
    """Identity-stable, type-grouped, hash-indexed fact store."""

    def __init__(self) -> None:
        self._facts: dict[int, FactHandle] = {}
        self._by_type: dict[str, set[int]] = defaultdict(set)
        # (fact_type, field) -> value -> {handle_id, ...}. Built lazily the first
        # time a join asks for it; maintained on every mutation thereafter.
        self._eq_index: dict[tuple[str, str], dict[Any, set[int]]] = {}
        self._ids = count(1)

    # --- lifecycle -----------------------------------------------------------

    def insert(self, fact_type: str, fields: dict[str, Any]) -> FactHandle:
        """Insert a fact and return its stable handle."""
        handle = FactHandle(id=next(self._ids), fact_type=fact_type, fields=dict(fields))
        self._facts[handle.id] = handle
        self._by_type[fact_type].add(handle.id)
        self._index_handle(handle)
        return handle

    def update(self, handle_id: int, fields: dict[str, Any]) -> FactHandle:
        """Replace a fact's fields in place, preserving identity.

        Raises:
            KeyError: if ``handle_id`` is not resident.
        """
        handle = self._facts[handle_id]
        self._deindex_handle(handle)
        handle.fields = dict(fields)
        self._index_handle(handle)
        return handle

    def retract(self, handle_id: int) -> FactHandle | None:
        """Remove a fact. Returns the removed handle, or ``None`` if absent."""
        handle = self._facts.pop(handle_id, None)
        if handle is None:
            return None
        self._by_type[handle.fact_type].discard(handle.id)
        self._deindex_handle(handle)
        return handle

    def clear(self) -> None:
        self._facts.clear()
        self._by_type.clear()
        self._eq_index.clear()

    # --- queries -------------------------------------------------------------

    def get(self, handle_id: int) -> FactHandle | None:
        return self._facts.get(handle_id)

    def by_type(self, fact_type: str) -> list[FactHandle]:
        """All resident facts of a type (insertion order is not guaranteed)."""
        return [self._facts[i] for i in self._by_type.get(fact_type, ())]

    def by_equality(self, fact_type: str, field: str, value: Any) -> list[FactHandle]:
        """Facts of ``fact_type`` whose ``field == value`` via the hash index.

        Building the index on first use keeps memory proportional to the join
        keys actually exercised, rather than indexing every field of every fact.
        """
        key = (fact_type, field)
        index = self._eq_index.get(key)
        if index is None:
            index = self._build_index(fact_type, field)
        return [self._facts[i] for i in index.get(value, ())]

    def __len__(self) -> int:
        return len(self._facts)

    def __iter__(self) -> Iterable[FactHandle]:
        return iter(self._facts.values())

    # --- index maintenance ---------------------------------------------------

    def _build_index(self, fact_type: str, field: str) -> dict[Any, set[int]]:
        index: dict[Any, set[int]] = defaultdict(set)
        for hid in self._by_type.get(fact_type, ()):
            fields = self._facts[hid].fields
            if field in fields:
                index[fields[field]].add(hid)
        self._eq_index[(fact_type, field)] = index
        return index

    def _index_handle(self, handle: FactHandle) -> None:
        for (ftype, field), index in self._eq_index.items():
            if ftype != handle.fact_type:
                continue
            if field in handle.fields:
                index[handle.fields[field]].add(handle.id)

    def _deindex_handle(self, handle: FactHandle) -> None:
        for (ftype, field), index in self._eq_index.items():
            if ftype != handle.fact_type:
                continue
            if field in handle.fields:
                bucket = index.get(handle.fields[field])
                if bucket is not None:
                    bucket.discard(handle.id)
                    if not bucket:
                        del index[handle.fields[field]]


__all__ = ["CrossFactWorkingMemory"]
