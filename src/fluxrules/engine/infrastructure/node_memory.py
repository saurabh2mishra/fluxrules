"""Node memory for caching partial match results across evaluations.

In streaming mode, when facts change incrementally, most condition
nodes produce the same result. NodeMemory caches results keyed by
the condition node identity and the relevant fact values.

Only used in streaming mode. In stateless mode, this is not instantiated.
"""

from __future__ import annotations

import threading
from collections import OrderedDict
from typing import Any


class NodeMemory:
    """Caches condition evaluation results at the node level (true LRU).

    In streaming mode, when facts change incrementally, most condition
    nodes produce the same result. NodeMemory caches results keyed by
    the condition node identity and the relevant fact values.

    This differs from per-cycle condition result caching in that:
    - Per-cycle caching works at the rule level (one evaluation cycle)
    - Node memory caches at the node level (across evaluations)

    Eviction is **least-recently-used**: the cache is an ``OrderedDict``; a
    read (:meth:`get` hit) and a write (:meth:`put`) move the key to the most-
    recently-used end, and on overflow the least-recently-used key is popped
    (``popitem(last=False)``). This bounds memory at ``max_entries`` while
    keeping the hot working set resident - unlike the prior "clear half the
    keys" scheme, which discarded recently-used entries arbitrarily and churned
    the cache under a high-cardinality fact stream.

    NodeMemory is only instantiated in streaming mode, which is single-stream
    by contract (one owning thread). The lock is retained as a defensive
    guard; under the contract it is essentially uncontended.

    Usage:
        node_mem = NodeMemory(max_entries=100_000)
        result = node_mem.get(rule_id, "condition.path", (field1_val, field2_val))
        if result is None:
            result = evaluate_condition(...)
            node_mem.put(rule_id, "condition.path", (field1_val, field2_val), result)
        node_mem.invalidate_field("field1")  # On fact change
    """

    def __init__(self, max_entries: int = 100_000) -> None:
        """Initialize node memory cache.

        Args:
            max_entries: Maximum cache entries before least-recently-used
                eviction. Must be >= 1.
        """
        self._cache: OrderedDict[tuple, bool] = OrderedDict()
        self._max_entries = max(1, max_entries)
        self._hits = 0
        self._misses = 0
        self._evictions = 0
        self._lock = threading.Lock()
        # Inverted index: maps each value found in a key's relevant_values to
        # the set of cache keys that contain that value.  Maintained in sync
        # with _cache so that invalidate_field() can look up exactly the keys
        # to evict in O(k) time (k = keys referencing the changed field)
        # instead of scanning the entire cache.
        self._field_to_keys: dict[Any, set] = {}

    def _index_key(self, key: tuple) -> None:
        """Add key to the field inverted index (called under _lock)."""
        _rule_id, _condition_path, relevant_values = key
        for v in relevant_values:
            entry = self._field_to_keys.get(v)
            if entry is None:
                self._field_to_keys[v] = {key}
            else:
                entry.add(key)

    def _unindex_key(self, key: tuple) -> None:
        """Remove key from the field inverted index (called under _lock)."""
        _rule_id, _condition_path, relevant_values = key
        for v in relevant_values:
            entry = self._field_to_keys.get(v)
            if entry is not None:
                entry.discard(key)
                if not entry:
                    del self._field_to_keys[v]

    def get(self, rule_id: int, condition_path: str, relevant_values: tuple) -> bool | None:
        """Look up a cached condition result, refreshing its LRU recency.

        A hit moves the key to the most-recently-used end so it survives
        eviction longer than colder entries.

        Args:
            rule_id: ID of the rule
            condition_path: Path to the condition node in the DSL tree
            relevant_values: Tuple of fact values relevant to this condition

        Returns:
            Cached boolean result, or None if not in cache
        """
        key = (rule_id, condition_path, relevant_values)
        with self._lock:
            # ``in`` (not ``.get() is not None``) so a cached ``False`` counts
            # as a hit rather than being mistaken for a miss.
            if key in self._cache:
                self._cache.move_to_end(key)
                self._hits += 1
                return self._cache[key]
            self._misses += 1
            return None

    def put(self, rule_id: int, condition_path: str, relevant_values: tuple, result: bool) -> None:
        """Cache a condition result, evicting the LRU entry on overflow.

        Args:
            rule_id: ID of the rule
            condition_path: Path to the condition node in the DSL tree
            relevant_values: Tuple of fact values relevant to this condition
            result: Boolean evaluation result to cache
        """
        key = (rule_id, condition_path, relevant_values)
        with self._lock:
            if key in self._cache:
                # Refresh value + recency without growing the cache.
                self._cache[key] = result
                self._cache.move_to_end(key)
                return
            self._cache[key] = result  # inserted at the MRU end
            self._index_key(key)       # register in the inverted index
            # Evict least-recently-used entries until within bounds.
            while len(self._cache) > self._max_entries:
                evicted_key, _ = self._cache.popitem(last=False)
                self._evictions += 1
                self._unindex_key(evicted_key)  # remove from inverted index

    def invalidate_field(self, field_name: str) -> None:
        """Invalidate all cache entries that depend on a specific field.

        Uses the inverted index (_field_to_keys) for O(k) complexity, where
        k = number of cache entries that reference the changed field.  This
        replaces the previous O(N) full-cache scan.

        Args:
            field_name: Name of the field that changed
        """
        with self._lock:
            # Pop the entire bucket for this field in one dict operation.
            keys_to_remove = self._field_to_keys.pop(field_name, None)
            if not keys_to_remove:
                return
            for key in keys_to_remove:
                self._cache.pop(key, None)
                # Clean up the key from every OTHER field bucket it was in so
                # the index stays consistent (the field_name bucket is already
                # gone; _unindex_key safely skips missing entries).
                self._unindex_key(key)

    def invalidate_fields(self, fields: set[str]) -> None:
        """Invalidate entries for multiple changed fields.

        Args:
            fields: Set of field names that changed
        """
        for f in fields:
            self.invalidate_field(f)

    def invalidate_all(self) -> None:
        """Invalidate the entire cache. Used when significant changes occur."""
        with self._lock:
            self._cache.clear()
            self._field_to_keys.clear()

    @property
    def hit_rate(self) -> float:
        """Return the cache hit rate as a fraction [0, 1]."""
        total = self._hits + self._misses
        return self._hits / total if total > 0 else 0.0

    def clear(self) -> None:
        """Clear all cache entries and statistics."""
        with self._lock:
            self._cache.clear()
            self._field_to_keys.clear()
            self._hits = 0
            self._misses = 0
            self._evictions = 0

    @property
    def stats(self) -> dict[str, Any]:
        """Return cache statistics for monitoring (feeds P2.4 metrics)."""
        total = self._hits + self._misses
        return {
            "entries": len(self._cache),
            "max_entries": self._max_entries,
            "hits": self._hits,
            "misses": self._misses,
            "evictions": self._evictions,
            "hit_rate": self.hit_rate,
            "total_accesses": total,
        }

    def __len__(self) -> int:
        """Return number of cached entries."""
        return len(self._cache)
