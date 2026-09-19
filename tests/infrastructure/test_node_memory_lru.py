"""LRU-eviction tests for NodeMemory (PHREAK P2.3).

The prior implementation evicted by deleting "half the keys" arbitrarily. P2.3
replaced it with a true ``OrderedDict``-backed LRU. These tests prove the
*kept/evicted* keys match true least-recently-used semantics (not half-clear),
that reads refresh recency, and that streaming access patterns behave correctly
(high hit rate for repeating facts; bounded LRU eviction for unique facts).
"""

import pytest

from fluxrules.engine.infrastructure.node_memory import NodeMemory


def _put(mem: NodeMemory, i: int, result: bool = True) -> None:
    mem.put(i, "root", (i,), result)


def _has(mem: NodeMemory, i: int) -> bool:
    return mem.get(i, "root", (i,)) is not None


class TestTrueLRUEviction:
    """Eviction order is least-recently-used, not arbitrary half-clear."""

    def test_evicts_least_recently_used_first(self):
        mem = NodeMemory(max_entries=3)
        _put(mem, 1)
        _put(mem, 2)
        _put(mem, 3)
        # Inserting a 4th evicts key 1 (the LRU), keeps 2,3,4.
        _put(mem, 4)
        assert len(mem) == 3
        assert not _has(mem, 1)  # evicted
        # Re-check membership without disturbing order via a fresh stats read.
        assert mem.stats["evictions"] == 1

    def test_read_refreshes_recency(self):
        """A get() hit must protect a key from being the next eviction victim."""
        mem = NodeMemory(max_entries=3)
        _put(mem, 1)
        _put(mem, 2)
        _put(mem, 3)
        # Touch key 1 so it becomes most-recently-used; key 2 is now the LRU.
        assert _has(mem, 1)
        _put(mem, 4)  # evicts key 2 (now the LRU), not key 1
        assert _has(mem, 1)
        assert _has(mem, 3)
        assert _has(mem, 4)
        assert not _has(mem, 2)

    def test_put_existing_key_refreshes_recency_without_growth(self):
        mem = NodeMemory(max_entries=3)
        _put(mem, 1)
        _put(mem, 2)
        _put(mem, 3)
        # Re-put key 1 -> refreshes recency, does NOT grow the cache.
        _put(mem, 1, result=False)
        assert len(mem) == 3
        _put(mem, 4)  # evicts key 2 (LRU), key 1 protected
        assert mem.get(1, "root", (1,)) is False
        assert not _has(mem, 2)

    def test_eviction_is_one_at_a_time_not_half_clear(self):
        """Overflow drops exactly one (the LRU), never half the cache."""
        mem = NodeMemory(max_entries=100)
        for i in range(100):
            _put(mem, i)
        assert len(mem) == 100
        # One more insert -> exactly one eviction; size stays at the cap.
        _put(mem, 100)
        assert len(mem) == 100
        assert mem.stats["evictions"] == 1
        # The half-clear scheme would have dropped ~50 here.

    def test_cached_false_is_a_hit_not_a_miss(self):
        """A cached False must register as a hit and refresh recency."""
        mem = NodeMemory(max_entries=2)
        mem.put(1, "root", (1,), False)
        assert mem.get(1, "root", (1,)) is False
        assert mem.stats["hits"] == 1
        assert mem.stats["misses"] == 0


class TestStreamingHitRate:
    """Repeating-fact streams hit; unique-fact streams evict in LRU order."""

    def test_repeating_facts_high_hit_rate(self):
        mem = NodeMemory(max_entries=1_000)
        # Warm a small working set.
        for i in range(10):
            _put(mem, i)
        mem.clear()  # reset stats; re-warm
        for i in range(10):
            _put(mem, i)
        # Stream the same 10 facts many times.
        for _ in range(500):
            for i in range(10):
                assert _has(mem, i)
        assert mem.hit_rate > 0.99
        assert mem.stats["evictions"] == 0  # working set fits

    def test_unique_facts_bounded_lru_no_unbounded_growth(self):
        cap = 256
        mem = NodeMemory(max_entries=cap)
        # Stream 10x the cap of unique facts.
        for i in range(cap * 10):
            _put(mem, i)
        # Cache never exceeds the cap; evictions account for the overflow.
        assert len(mem) == cap
        assert mem.stats["entries"] == cap
        assert mem.stats["evictions"] == cap * 10 - cap
        # Only the most-recent ``cap`` unique keys survive (true LRU window).
        recent_survivors = sum(1 for i in range(cap * 10 - cap, cap * 10) if _has(mem, i))
        assert recent_survivors == cap

    def test_max_entries_floor_is_one(self):
        """max_entries < 1 is clamped to 1 (never a zero-capacity cache)."""
        mem = NodeMemory(max_entries=0)
        _put(mem, 1)
        _put(mem, 2)
        assert len(mem) == 1
        assert _has(mem, 2)
        assert not _has(mem, 1)


class TestStatsExposed:
    """Stats expose hit/eviction accounting for P2.4 metrics."""

    def test_stats_shape(self):
        mem = NodeMemory(max_entries=8)
        _put(mem, 1)
        _has(mem, 1)
        _has(mem, 99)
        stats = mem.stats
        for key in (
            "entries",
            "max_entries",
            "hits",
            "misses",
            "evictions",
            "hit_rate",
            "total_accesses",
        ):
            assert key in stats
        assert stats["max_entries"] == 8


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
