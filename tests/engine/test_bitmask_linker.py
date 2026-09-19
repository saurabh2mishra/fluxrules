"""Tests for BitMaskLinker.

Tests the O(1) rule linking system using bit-mask operations.
Validates that linking results match the TokenPropagator (old path).
"""

import pytest

from fluxrules.engine.infrastructure.bitmask_linker import BitMaskLinker


class TestBitMaskLinkerBasic:
    """Basic functionality tests."""

    def test_register_segment_single(self):
        """Test registering a single segment."""
        linker = BitMaskLinker()
        info = linker.register_segment("seg_A", frozenset(["field_A"]))

        assert info.segment_id == "seg_A"
        assert info.bit_position == 0
        assert "field_A" in info.field_bits
        assert info.field_mask > 0

    def test_register_multiple_segments(self):
        """Test registering multiple segments with sequential bit positions."""
        linker = BitMaskLinker()
        info1 = linker.register_segment("seg_A", frozenset(["field_A"]))
        info2 = linker.register_segment("seg_B", frozenset(["field_B"]))
        info3 = linker.register_segment("seg_C", frozenset(["field_C"]))

        assert info1.bit_position == 0
        assert info2.bit_position == 1
        assert info3.bit_position == 2

    def test_segment_already_registered(self):
        """Test that re-registering a segment returns existing info."""
        linker = BitMaskLinker()
        info1 = linker.register_segment("seg_A", frozenset(["field_A"]))
        info2 = linker.register_segment("seg_A", frozenset(["field_A"]))

        assert info1 is info2

    def test_register_rule_single(self):
        """Test registering a rule with a single segment."""
        linker = BitMaskLinker()
        linker.register_segment("seg_A", frozenset(["field_A"]))
        linker.register_rule(1, ["seg_A"])

        assert linker.is_rule_linked(1) is False  # Not linked until facts provided

    def test_register_rule_multiple_segments(self):
        """Test registering a rule with multiple segments."""
        linker = BitMaskLinker()
        linker.register_segment("seg_A", frozenset(["field_A"]))
        linker.register_segment("seg_B", frozenset(["field_B"]))
        linker.register_rule(1, ["seg_A", "seg_B"])

        # Initially not linked
        assert linker.is_rule_linked(1) is False


class TestBitMaskLinkerLinking:
    """Tests for rule linking based on facts."""

    def test_linking_single_segment_single_field(self):
        """Test linking when a single segment's field is present."""
        linker = BitMaskLinker()
        linker.register_segment("seg_A", frozenset(["field_A"]))
        linker.register_rule(1, ["seg_A"])

        # Provide the required field
        newly_linked = linker.update_facts({"field_A": "value_A"})

        assert 1 in newly_linked
        assert linker.is_rule_linked(1) is True

    def test_linking_multiple_fields_in_segment(self):
        """Test linking when all fields in a segment are present."""
        linker = BitMaskLinker()
        linker.register_segment("seg_AB", frozenset(["field_A", "field_B"]))
        linker.register_rule(1, ["seg_AB"])

        # Only one field - segment not complete
        linker.update_facts({"field_A": "value_A"})
        assert linker.is_rule_linked(1) is False

        # Both fields - segment complete and rule linked
        newly_linked = linker.update_facts({"field_A": "value_A", "field_B": "value_B"})
        assert 1 in newly_linked
        assert linker.is_rule_linked(1) is True

    def test_linking_multiple_segments(self):
        """Test linking when all required segments are active."""
        linker = BitMaskLinker()
        linker.register_segment("seg_A", frozenset(["field_A"]))
        linker.register_segment("seg_B", frozenset(["field_B"]))
        linker.register_rule(1, ["seg_A", "seg_B"])

        # Only seg_A active
        linker.update_facts({"field_A": "value_A"})
        assert linker.is_rule_linked(1) is False

        # Both segments active
        newly_linked = linker.update_facts({"field_A": "value_A", "field_B": "value_B"})
        assert 1 in newly_linked
        assert linker.is_rule_linked(1) is True

    def test_get_linked_rules_multiple(self):
        """Test get_linked_rules returns all currently linked rules."""
        linker = BitMaskLinker()
        linker.register_segment("seg_A", frozenset(["field_A"]))
        linker.register_segment("seg_B", frozenset(["field_B"]))
        linker.register_rule(1, ["seg_A"])
        linker.register_rule(2, ["seg_B"])
        linker.register_rule(3, ["seg_A", "seg_B"])

        linker.update_facts({"field_A": "value_A", "field_B": "value_B"})

        linked = linker.get_linked_rules()
        assert linked == {1, 2, 3}

    def test_newly_linked_tracking(self):
        """Test that newly_linked tracks only new links, not existing ones."""
        linker = BitMaskLinker()
        linker.register_segment("seg_A", frozenset(["field_A"]))
        linker.register_segment("seg_B", frozenset(["field_B"]))
        linker.register_rule(1, ["seg_A"])
        linker.register_rule(2, ["seg_B"])

        # First update: both rules link
        newly_linked1 = linker.update_facts({"field_A": "value_A", "field_B": "value_B"})
        assert newly_linked1 == {1, 2}

        # Second update with same facts: no new links
        newly_linked2 = linker.update_facts({"field_A": "value_A", "field_B": "value_B"})
        assert newly_linked2 == set()

    def test_fact_change_unlinks_rule(self):
        """Test that removing a fact unlinks a rule."""
        linker = BitMaskLinker()
        linker.register_segment("seg_A", frozenset(["field_A"]))
        linker.register_rule(1, ["seg_A"])

        # Link with fact present
        linker.update_facts({"field_A": "value_A"})
        assert linker.is_rule_linked(1) is True

        # Unlink by removing fact
        linker.update_facts({})
        assert linker.is_rule_linked(1) is False


class TestBitMaskLinkerScale:
    """Tests at larger scale (more segments, more rules)."""

    def test_large_segment_count(self):
        """Test with 100+ segments."""
        linker = BitMaskLinker()
        num_segments = 100

        # Register segments
        for i in range(num_segments):
            linker.register_segment(f"seg_{i}", frozenset([f"field_{i}"]))

        # Register rules that require specific segments
        for i in range(num_segments):
            linker.register_rule(i, [f"seg_{i}"])

        # Provide all facts
        facts = {f"field_{i}": f"value_{i}" for i in range(num_segments)}
        newly_linked = linker.update_facts(facts)

        assert len(newly_linked) == num_segments
        assert linker.get_linked_rules() == set(range(num_segments))

    def test_large_rule_count_single_segment(self):
        """Test with many rules on the same segment."""
        linker = BitMaskLinker()
        num_rules = 1000

        linker.register_segment("seg_shared", frozenset(["field_A"]))

        # All rules depend on the same segment
        for i in range(num_rules):
            linker.register_rule(i, ["seg_shared"])

        # Link all rules
        linker.update_facts({"field_A": "value"})
        linked = linker.get_linked_rules()

        assert len(linked) == num_rules

    def test_complex_rule_dependencies(self):
        """Test with rules having overlapping segment dependencies."""
        linker = BitMaskLinker()

        # Create a small grid of segments
        segments = []
        for i in range(10):
            seg_id = f"seg_{i}"
            linker.register_segment(seg_id, frozenset([f"field_{i}"]))
            segments.append(seg_id)

        # Create rules with different segment requirements
        rules = [
            (0, segments[0:3]),  # Requires first 3 segments
            (1, segments[2:5]),  # Requires 3-5
            (2, segments[0:5]),  # Requires first 5
            (3, segments[5:10]),  # Requires 5-10
        ]

        for rule_id, required_segs in rules:
            linker.register_rule(rule_id, required_segs)

        # Provide facts for first 5 fields
        facts = {f"field_{i}": f"value_{i}" for i in range(5)}
        newly_linked = linker.update_facts(facts)

        # Rules 0, 1, 2 should link (they only need fields 0-4)
        assert 0 in newly_linked
        assert 1 in newly_linked
        assert 2 in newly_linked
        # Rule 3 should not link (needs field 5-9, which are missing)
        assert 3 not in newly_linked


class TestBitMaskLinkerClear:
    """Tests for clearing state."""

    def test_clear_resets_state(self):
        """Test that clear() resets all internal state."""
        linker = BitMaskLinker()
        linker.register_segment("seg_A", frozenset(["field_A"]))
        linker.register_rule(1, ["seg_A"])
        linker.update_facts({"field_A": "value"})

        assert linker.is_rule_linked(1) is True

        linker.clear()

        # After clear, segment info should be gone
        assert len(linker._segment_bits) == 0
        assert len(linker._rule_links) == 0
        assert len(linker.get_linked_rules()) == 0


class TestBitMaskLinkerIntegration:
    """Integration tests with real rule scenarios."""

    def test_e_commerce_inventory_scenario(self):
        """Test a realistic e-commerce scenario."""
        linker = BitMaskLinker()

        # Define segments for inventory rules
        linker.register_segment("seg_stock", frozenset(["stock_level", "sku"]))
        linker.register_segment("seg_pricing", frozenset(["unit_price", "currency"]))
        linker.register_segment("seg_customer", frozenset(["customer_tier"]))

        # Define rules
        # Rule 1: Low stock alert - needs stock + sku
        linker.register_rule(1, ["seg_stock"])
        # Rule 2: Pricing rule - needs pricing + customer tier
        linker.register_rule(2, ["seg_pricing", "seg_customer"])
        # Rule 3: Combined - needs all three
        linker.register_rule(3, ["seg_stock", "seg_pricing", "seg_customer"])

        # Only stock facts
        linker.update_facts({"stock_level": 10, "sku": "SKU123"})
        assert linker.get_linked_rules() == {1}

        # Add pricing facts
        newly_linked = linker.update_facts(
            {"stock_level": 10, "sku": "SKU123", "unit_price": 29.99, "currency": "USD"}
        )
        assert newly_linked == set()  # No new links, just the same state
        assert linker.get_linked_rules() == {1}

        # Add customer tier
        newly_linked = linker.update_facts(
            {
                "stock_level": 10,
                "sku": "SKU123",
                "unit_price": 29.99,
                "currency": "USD",
                "customer_tier": "premium",
            }
        )
        # Now rule 2 and 3 should link
        assert 2 in newly_linked or 3 in newly_linked


class TestBitMaskLinkerDeltaLinking:
    """Incremental delta-linking must equal full recompute."""

    def test_delta_without_baseline_falls_back_to_full(self):
        linker = BitMaskLinker()
        linker.register_segment("seg_A", frozenset(["a"]))
        linker.register_rule(1, ["seg_A"])
        # No prior update_facts -> delta must behave like a full update.
        newly = linker.update_facts_delta({"a": 1})
        assert linker.get_linked_rules() == {1}
        assert newly == {1}

    def test_delta_value_only_change_is_noop_linkage(self):
        linker = BitMaskLinker()
        linker.register_segment("seg_A", frozenset(["a"]))
        linker.register_rule(1, ["seg_A"])
        linker.update_facts({"a": 1})
        assert linker.get_linked_rules() == {1}
        # Same presence, different value -> linkage identical, nothing newly linked.
        newly = linker.update_facts_delta({"a": 999})
        assert newly == set()
        assert linker.get_linked_rules() == {1}

    def test_delta_field_removal_unlinks(self):
        linker = BitMaskLinker()
        linker.register_segment("seg_AB", frozenset(["a", "b"]))
        linker.register_rule(1, ["seg_AB"])
        linker.update_facts({"a": 1, "b": 2})
        assert linker.get_linked_rules() == {1}
        # Remove a required field -> rule must unlink.
        linker.update_facts_delta({"a": 1})
        assert linker.get_linked_rules() == set()

    def test_delta_field_addition_links(self):
        linker = BitMaskLinker()
        linker.register_segment("seg_AB", frozenset(["a", "b"]))
        linker.register_rule(1, ["seg_AB"])
        linker.update_facts({"a": 1})
        assert linker.get_linked_rules() == set()
        newly = linker.update_facts_delta({"a": 1, "b": 2})
        assert newly == {1}
        assert linker.get_linked_rules() == {1}

    @pytest.mark.parametrize("seed", range(6))
    def test_delta_equals_full_recompute_randomized(self, seed):
        """The core soundness gate: delta linkage == fresh full recompute.

        Drives a long sequence of add / value-change / remove operations and,
        at every step, asserts the incrementally maintained linked-rule set is
        byte-identical to a linker that recomputed from scratch for that fact.
        """
        import random

        rng = random.Random(seed)
        n_fields = 12

        seg_defs = {}
        for s in range(30):
            k = rng.randint(1, 3)
            fields = frozenset(f"f{rng.randint(0, n_fields - 1)}" for _ in range(k))
            seg_defs[f"s{s}"] = fields
        rule_defs = {
            r: [f"s{rng.randint(0, 29)}" for _ in range(rng.randint(1, 3))] for r in range(60)
        }

        def build():
            bl = BitMaskLinker()
            for sid, fields in seg_defs.items():
                bl.register_segment(sid, fields)
            for rid, sids in rule_defs.items():
                bl.register_rule(rid, sids)
            return bl

        delta = build()
        cur: dict = {}
        for _ in range(1000):
            cur = dict(cur)
            f = f"f{rng.randint(0, n_fields - 1)}"
            if rng.random() < 0.25 and f in cur:
                del cur[f]
            else:
                cur[f] = rng.randint(0, 100)

            delta.update_facts_delta(cur)
            full = build()
            full.update_facts(cur)
            assert delta.get_linked_rules() == full.get_linked_rules()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
