"""Tests for NodeMemory.

Tests the node-level condition caching system for streaming mode.
"""

import pytest

from fluxrules.engine.infrastructure.node_memory import NodeMemory


class TestNodeMemoryBasic:
    """Basic functionality tests."""

    def test_cache_miss(self):
        """Test that cache miss returns None."""
        mem = NodeMemory()
        result = mem.get(1, "condition.0", ("value1",))
        assert result is None

    def test_cache_hit(self):
        """Test that cached values are returned."""
        mem = NodeMemory()
        mem.put(1, "condition.0", ("value1",), True)

        result = mem.get(1, "condition.0", ("value1",))
        assert result is True

    def test_cache_different_keys(self):
        """Test that different keys don't collide."""
        mem = NodeMemory()
        mem.put(1, "condition.0", ("value1",), True)
        mem.put(2, "condition.0", ("value1",), False)

        result1 = mem.get(1, "condition.0", ("value1",))
        result2 = mem.get(2, "condition.0", ("value1",))

        assert result1 is True
        assert result2 is False

    def test_cache_different_condition_paths(self):
        """Test that different condition paths don't collide."""
        mem = NodeMemory()
        mem.put(1, "condition.0", ("value1",), True)
        mem.put(1, "condition.1", ("value1",), False)

        result0 = mem.get(1, "condition.0", ("value1",))
        result1 = mem.get(1, "condition.1", ("value1",))

        assert result0 is True
        assert result1 is False

    def test_cache_different_values(self):
        """Test that different values don't collide."""
        mem = NodeMemory()
        mem.put(1, "condition.0", ("value1",), True)
        mem.put(1, "condition.0", ("value2",), False)

        result1 = mem.get(1, "condition.0", ("value1",))
        result2 = mem.get(1, "condition.0", ("value2",))

        assert result1 is True
        assert result2 is False


class TestNodeMemoryStats:
    """Tests for hit rate statistics."""

    def test_hit_rate_all_hits(self):
        """Test hit rate when all accesses hit."""
        mem = NodeMemory()
        mem.put(1, "condition.0", ("value1",), True)

        mem.get(1, "condition.0", ("value1",))
        mem.get(1, "condition.0", ("value1",))
        mem.get(1, "condition.0", ("value1",))

        assert mem.hit_rate == 1.0

    def test_hit_rate_all_misses(self):
        """Test hit rate when all accesses miss."""
        mem = NodeMemory()
        mem.get(1, "condition.0", ("value1",))
        mem.get(1, "condition.0", ("value2",))
        mem.get(1, "condition.0", ("value3",))

        assert mem.hit_rate == 0.0

    def test_hit_rate_mixed(self):
        """Test hit rate with mixed hits and misses."""
        mem = NodeMemory()
        mem.put(1, "condition.0", ("value1",), True)
        mem.put(1, "condition.1", ("value2",), False)

        mem.get(1, "condition.0", ("value1",))  # hit
        mem.get(1, "condition.1", ("value2",))  # hit
        mem.get(1, "condition.2", ("value3",))  # miss
        mem.get(1, "condition.3", ("value4",))  # miss

        assert mem.hit_rate == 0.5

    def test_stats_dict(self):
        """Test stats() returns all statistics."""
        mem = NodeMemory()
        mem.put(1, "condition.0", ("value1",), True)
        mem.get(1, "condition.0", ("value1",))  # hit
        mem.get(2, "condition.0", ("value2",))  # miss

        stats = mem.stats
        assert stats["hits"] == 1
        assert stats["misses"] == 1
        assert stats["hit_rate"] == 0.5
        assert stats["entries"] == 1
        assert stats["total_accesses"] == 2


class TestNodeMemoryEviction:
    """Tests for cache eviction when max_entries is exceeded."""

    def test_eviction_on_max_entries(self):
        """Test that eviction occurs when cache is full."""
        mem = NodeMemory(max_entries=5)

        # Fill the cache
        for i in range(5):
            mem.put(i, "condition.0", (f"value_{i}",), True)

        assert len(mem) == 5

        # Adding one more should trigger eviction
        mem.put(5, "condition.0", ("value_5",), True)

        # Cache should still be bounded (roughly half)
        assert len(mem) <= 5

    def test_entries_len(self):
        """Test __len__ returns number of cached entries."""
        mem = NodeMemory()
        assert len(mem) == 0

        mem.put(1, "condition.0", ("value1",), True)
        assert len(mem) == 1

        mem.put(2, "condition.0", ("value2",), False)
        assert len(mem) == 2


class TestNodeMemoryInvalidation:
    """Tests for cache invalidation."""

    def test_invalidate_all(self):
        """Test invalidate_all clears all entries."""
        mem = NodeMemory()
        mem.put(1, "condition.0", ("value1",), True)
        mem.put(2, "condition.1", ("value2",), False)

        assert len(mem) == 2

        mem.invalidate_all()

        assert len(mem) == 0
        assert mem.hit_rate == 0.0

    def test_clear_resets_stats(self):
        """Test that clear() resets statistics."""
        mem = NodeMemory()
        mem.put(1, "condition.0", ("value1",), True)
        mem.get(1, "condition.0", ("value1",))  # hit
        mem.get(1, "condition.0", ("value2",))  # miss

        assert mem.stats["total_accesses"] == 2

        mem.clear()

        assert len(mem) == 0
        assert mem.stats["total_accesses"] == 0
        assert mem.hit_rate == 0.0

    def test_invalidate_field(self):
        """Test field invalidation removes entries that depend on that field.

        relevant_fields must be passed to put() so the inverted index maps
        field names → cache keys.  Entries stored without relevant_fields are
        not indexed and are not affected by invalidate_field().
        """
        mem = NodeMemory()
        # Rule 1 depends on field_A (value 42) and field_C (value 99)
        mem.put(1, "condition.0", (42, 99), True, relevant_fields=("field_A", "field_C"))
        # Rule 2 depends only on field_B (value 7) — must survive invalidation of field_A
        mem.put(2, "condition.0", (7,), False, relevant_fields=("field_B",))
        # Rule 3 stored without relevant_fields — not indexed, must survive
        mem.put(3, "condition.0", (42,), True)

        mem.invalidate_field("field_A")

        # Rule 1 evicted (depends on field_A)
        assert mem.get(1, "condition.0", (42, 99)) is None
        # Rule 2 kept (depends only on field_B)
        assert mem.get(2, "condition.0", (7,)) is False
        # Rule 3 kept (not indexed)
        assert mem.get(3, "condition.0", (42,)) is True

    def test_invalidate_fields(self):
        """Test invalidating multiple fields evicts all dependent entries."""
        mem = NodeMemory()
        mem.put(1, "condition.0", (10, 20), True, relevant_fields=("age", "amount"))
        mem.put(2, "condition.0", (30,), False, relevant_fields=("score",))

        mem.invalidate_fields({"age", "amount"})

        # Rule 1 evicted (depends on age and amount)
        assert mem.get(1, "condition.0", (10, 20)) is None
        # Rule 2 kept (depends on score, not affected)
        assert mem.get(2, "condition.0", (30,)) is False


class TestNodeMemoryStreaming:
    """Tests simulating streaming mode usage."""

    def test_streaming_warmup_hits(self):
        """Test that repeated evaluations get high hit rate."""
        mem = NodeMemory()

        # Warmup phase: cache various condition results
        for _ in range(3):
            mem.put(1, "condition.0", ("user_id_123", "age_25"), True)
            mem.put(1, "condition.1", ("status_active",), True)
            mem.put(1, "condition.2", ("score_95",), False)

        # Query phase: same facts repeated
        for _ in range(100):
            mem.get(1, "condition.0", ("user_id_123", "age_25"))
            mem.get(1, "condition.1", ("status_active",))
            mem.get(1, "condition.2", ("score_95",))

        # Hit rate should be very high
        assert mem.hit_rate > 0.99

    def test_streaming_fact_change(self):
        """Test handling fact changes in streaming.

        relevant_fields must be supplied so invalidate_field() finds the entry.
        The cache key uses the fact VALUE (25); the field index uses the field
        NAME ("age") — these are distinct.
        """
        mem = NodeMemory()

        # Initial facts: age=25, condition depends on field "age"
        mem.put(1, "condition.0", (25,), True, relevant_fields=("age",))
        mem.get(1, "condition.0", (25,))

        # Age field changes — invalidate by field name, not by value
        mem.invalidate_field("age")
        # Should get a miss
        result = mem.get(1, "condition.0", (25,))
        assert result is None

        # Cache new result for new age
        mem.put(1, "condition.0", ("age_30",), False)
        result = mem.get(1, "condition.0", ("age_30",))
        assert result is False


class TestNodeMemoryStress:
    """Stress and performance tests."""

    def test_many_entries(self):
        """Test with many cache entries."""
        mem = NodeMemory(max_entries=10_000)

        # Add many entries
        for rule_id in range(100):
            for node_id in range(50):
                key = (f"rule_{rule_id}", f"node_{node_id}")
                mem.put(rule_id, f"condition.{node_id}", key, True)

        assert len(mem) <= 10_000

        # Verify some entries still exist
        result = mem.get(0, "condition.0", ("rule_0", "node_0"))
        assert result is not None

    def test_large_value_tuples(self):
        """Test with large value tuples."""
        mem = NodeMemory()

        # Create a large tuple of values
        large_tuple = tuple(f"value_{i}" for i in range(100))

        mem.put(1, "condition.0", large_tuple, True)
        result = mem.get(1, "condition.0", large_tuple)

        assert result is True

    def test_throughput_with_high_hit_rate(self):
        """Test cache access throughput with high hit rate.

        This is a simple performance test to ensure caching doesn't
        add significant overhead.
        """
        mem = NodeMemory()
        mem.put(1, "condition.0", ("value1",), True)

        # Access cache many times
        for _ in range(10_000):
            result = mem.get(1, "condition.0", ("value1",))
            assert result is True

        # Should have very high hit rate
        assert mem.hit_rate > 0.999


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
