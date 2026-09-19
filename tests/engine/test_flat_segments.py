"""Tests for flat segment building (PHREAK P2.1).

The segment network groups rules by their condition field-set into **flat**
segments. A prior design synthesized ``is_shared`` parent segments with
``parent_id``/``child_ids`` links, but no rule was ever mapped to a parent, so
the hierarchy did real work that changed nothing while costing an O(S^2) build
at load. P2.1 removed it. These tests pin the flat contract so the dead
hierarchy cannot silently return.
"""

import pytest

from fluxrules import Rule
from fluxrules.engine.infrastructure.segment_network import Segment, SegmentNetwork


def _and_rule(rid: int, fields: list[str]) -> Rule:
    return Rule(
        id=rid,
        name=f"rule{rid}",
        condition_dsl={
            "type": "and",
            "conditions": [
                {"type": "condition", "field": f, "operator": ">", "value": 1} for f in fields
            ],
        },
        action="log",
        priority=1,
        persist=False,
    )


class TestSegmentIsFlat:
    """The Segment dataclass carries no hierarchy fields (P2.1 removal)."""

    def test_segment_has_no_hierarchy_attributes(self):
        seg = Segment(segment_id="seg_a", fields=frozenset({"a"}))
        assert not hasattr(seg, "parent_id")
        assert not hasattr(seg, "child_ids")
        assert not hasattr(seg, "is_shared")

    def test_network_has_no_build_hierarchy(self):
        network = SegmentNetwork()
        assert not hasattr(network, "_build_hierarchy")


class TestFlatSegmentGrouping:
    """Rules are grouped into flat field-set segments, never parents."""

    def test_single_rule_single_segment(self):
        network = SegmentNetwork()
        network.add_rules([_and_rule(1, ["age"])])
        segments = list(network.segments.values())
        assert len(segments) == 1
        assert segments[0].fields == frozenset({"age"})

    def test_disjoint_rules_distinct_segments(self):
        network = SegmentNetwork()
        network.add_rules([_and_rule(1, ["age"]), _and_rule(2, ["status"])])
        field_sets = {seg.fields for seg in network.segments.values()}
        assert frozenset({"age"}) in field_sets
        assert frozenset({"status"}) in field_sets

    def test_shared_fields_do_not_synthesize_parent(self):
        """Rules with overlapping fields must NOT create a synthetic parent.

        Pre-P2.1 this created a ``seg_shared_*`` parent segment; now the network
        only holds the rules' own flat field-set segments.
        """
        network = SegmentNetwork()
        network.add_rules(
            [
                _and_rule(1, ["age", "status", "score"]),
                _and_rule(2, ["age", "status", "credits"]),
            ]
        )
        # No segment id should be a synthesized shared parent.
        assert all(not seg_id.startswith("seg_shared_") for seg_id in network.segments)
        # Exactly the two rules' own field-set segments exist.
        field_sets = {seg.fields for seg in network.segments.values()}
        assert frozenset({"age", "status", "score"}) in field_sets
        assert frozenset({"age", "status", "credits"}) in field_sets

    def test_identical_field_set_rules_share_one_segment(self):
        network = SegmentNetwork()
        network.add_rules([_and_rule(1, ["age", "status"]), _and_rule(2, ["age", "status"])])
        # Both rules map to the same flat segment keyed by {age, status}.
        seg1 = network.get_segments_for_rule(1)
        seg2 = network.get_segments_for_rule(2)
        assert len(seg1) == 1 and len(seg2) == 1
        assert seg1[0].segment_id == seg2[0].segment_id
        assert seg1[0].rule_ids == {1, 2}


class TestFlatSegmentQueries:
    """Queries still work over the flat structure."""

    def test_get_segments_for_rule(self):
        network = SegmentNetwork()
        network.add_rules([_and_rule(1, ["f1", "f2"])])
        assert len(network.get_segments_for_rule(1)) == 1

    def test_get_affected_segments(self):
        network = SegmentNetwork()
        network.add_rules([_and_rule(1, ["age", "status"])])
        affected = network.get_affected_segments({"age"})
        assert len(affected) > 0


class TestFlatSegmentScale:
    """Many rules with a shared field stay flat (no parent explosion)."""

    def test_large_rule_set_with_shared_field_stays_flat(self):
        network = SegmentNetwork()
        rules = [_and_rule(i, ["common", f"unique_field_{i}"]) for i in range(20)]
        network.add_rules(rules)
        # No synthesized parent segments.
        assert all(not seg_id.startswith("seg_shared_") for seg_id in network.segments)
        # One flat segment per distinct field-set (all distinct here) => 20.
        assert len(network.segments) == 20


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
