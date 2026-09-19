"""Bit-mask based rule linking for O(1) rule activation checks.

Implements the Drools Phreak bit-mask linking pattern:
- Each segment has a bit position in a global mask
- Each field in a segment has a bit position in the segment mask
- A segment is "on" when all its field bits are on
- A rule is "linked" when all its segment bits are on

This provides O(1) rule linking checks instead of O(F) set-subset operations.
"""

from __future__ import annotations

from dataclasses import dataclass
from dataclasses import field as dc_field
from typing import Any


@dataclass
class SegmentBitInfo:
    """Bit position info for a segment."""

    segment_id: str
    bit_position: int  # Position in the global bit-mask
    field_bits: dict[str, int] = dc_field(
        default_factory=dict
    )  # field_name → bit position within segment
    field_mask: int = 0  # All field bits OR'd together
    current_state: int = 0  # Current active field bits


@dataclass
class RuleLinkInfo:
    """Linking info for a rule."""

    rule_id: int
    required_segment_mask: int  # Bits for all required segments
    is_linked: bool = False


class BitMaskLinker:
    """O(1) rule linking using layered bit-masks.

    Replaces O(F) set-subset checks with O(1) bit-mask operations.
    Implements the Drools Phreak pattern for efficient rule activation.

    Usage:
        linker = BitMaskLinker()
        linker.register_segment("seg_id", {"field1", "field2"})
        linker.register_rule(rule_id, ["seg_id"])
        newly_linked = linker.update_facts({"field1": value, "field2": value})
        linked_rules = linker.get_linked_rules()
    """

    def __init__(self) -> None:
        self._segment_bits: dict[str, SegmentBitInfo] = {}
        self._rule_links: dict[int, RuleLinkInfo] = {}
        self._global_state: int = 0  # Which segments are currently active
        self._next_segment_bit: int = 0
        self._linked_rules: set[int] = set()  # Rules currently linked

        # reverse indexes so streaming
        # updates touch only the structures affected by changed fields instead
        # of rebuilding from the full rule set every fact.
        # field name -> segment ids that reference it.
        self._field_to_segments: dict[str, set[str]] = {}
        # segment bit position -> rule ids requiring that segment.
        self._segbit_to_rules: dict[int, set[int]] = {}
        # Presence snapshot from the last update, used to compute the delta.
        self._present_fields: set[str] = set()
        # Whether a full (non-incremental) update has run since the last
        # structural change. Incremental updates require a valid baseline.
        self._has_baseline: bool = False

    def register_segment(self, segment_id: str, fields: frozenset[str]) -> SegmentBitInfo:
        """Assign bit positions to a segment and its fields.

        Args:
            segment_id: Unique segment identifier
            fields: Fields that this segment requires

        Returns:
            SegmentBitInfo with bit position assignments
        """
        if segment_id in self._segment_bits:
            return self._segment_bits[segment_id]

        bit_pos = self._next_segment_bit
        self._next_segment_bit += 1

        field_bits = {}
        field_mask = 0
        for i, f in enumerate(sorted(fields)):
            field_bit = 1 << i
            field_bits[f] = field_bit
            field_mask |= field_bit

        info = SegmentBitInfo(
            segment_id=segment_id,
            bit_position=bit_pos,
            field_bits=field_bits,
            field_mask=field_mask,
        )
        self._segment_bits[segment_id] = info
        # index fields -> segments and invalidate the delta baseline
        # (structure changed, so the next update must do a full pass).
        for f in field_bits:
            self._field_to_segments.setdefault(f, set()).add(segment_id)
        self._has_baseline = False
        return info

    def register_rule(self, rule_id: int, segment_ids: list[str]) -> None:
        """Register which segments a rule requires.

        Args:
            rule_id: Unique rule identifier
            segment_ids: List of segment IDs this rule depends on
        """
        mask = 0
        for sid in segment_ids:
            if sid in self._segment_bits:
                seg_bit = 1 << self._segment_bits[sid].bit_position
                mask |= seg_bit
        self._rule_links[rule_id] = RuleLinkInfo(rule_id=rule_id, required_segment_mask=mask)
        # index segment-bit -> rules so an incremental update can
        # re-link only the rules whose segments toggled. Invalidate baseline.
        for sid in segment_ids:
            info = self._segment_bits.get(sid)
            if info is not None:
                self._segbit_to_rules.setdefault(info.bit_position, set()).add(rule_id)
        self._has_baseline = False

    def update_facts(self, facts: dict[str, Any]) -> set[int]:
        """Update field bits based on present facts (full recompute).

        Returns:
            Set of newly linked rule IDs (not linked in previous state)
        """
        fact_fields = set(facts.keys())
        previously_linked = set(self._linked_rules)

        # Update each segment's state
        self._global_state = 0
        for seg_id, seg_info in self._segment_bits.items():
            seg_info.current_state = 0
            for field_name, bit in seg_info.field_bits.items():
                if field_name in fact_fields:
                    seg_info.current_state |= bit
            # Segment is active if all its field bits are on
            if seg_info.current_state == seg_info.field_mask:
                segment_bit = 1 << seg_info.bit_position
                self._global_state |= segment_bit

        # Check which rules are now linked
        self._linked_rules.clear()
        for rule_id, link_info in self._rule_links.items():
            if link_info.required_segment_mask == 0:
                continue
            linked = (
                self._global_state & link_info.required_segment_mask
            ) == link_info.required_segment_mask
            link_info.is_linked = linked
            if linked:
                self._linked_rules.add(rule_id)

        # record the presence baseline so subsequent streaming
        # updates can run incrementally via ``update_facts_delta``.
        self._present_fields = fact_fields
        self._has_baseline = True

        return self._linked_rules - previously_linked  # Newly linked

    def update_facts_delta(self, facts: dict[str, Any]) -> set[int]:
        """Incrementally update linking when only a few fields changed.

        Incremental delta-linking. Segment activation depends
        ONLY on which fields are *present*, never on their values. So when the
        set of present field names is unchanged versus the last update, the
        global segment state and every rule's linked status are identical and
        no work is required. When presence does change, only segments that
        contain an added/removed field can toggle, and only rules requiring
        those segments can change linkage - so we touch just those.

        Falls back to a full :meth:`update_facts` when there is no valid
        baseline (first call, or structure changed since the last update).

        Returns:
            Set of newly linked rule IDs (not linked in the previous state).
        """
        if not self._has_baseline:
            return self.update_facts(facts)

        new_fields = set(facts.keys())
        changed_fields = new_fields ^ self._present_fields  # symmetric difference
        if not changed_fields:
            # Identical field presence -> identical linkage. Nothing toggled.
            self._present_fields = new_fields
            return set()

        previously_linked = set(self._linked_rules)

        # Only segments referencing a changed field can flip state.
        affected_segments: set[str] = set()
        for f in changed_fields:
            segs = self._field_to_segments.get(f)
            if segs:
                affected_segments.update(segs)

        # Recompute just those segments and collect rules whose segment bits
        # toggled (became active or inactive).
        toggled_segment_bits: list[int] = []
        for seg_id in affected_segments:
            seg_info = self._segment_bits[seg_id]
            segment_bit = 1 << seg_info.bit_position
            was_active = bool(self._global_state & segment_bit)
            seg_info.current_state = 0
            for field_name, bit in seg_info.field_bits.items():
                if field_name in new_fields:
                    seg_info.current_state |= bit
            now_active = seg_info.current_state == seg_info.field_mask
            if now_active and not was_active:
                self._global_state |= segment_bit
                toggled_segment_bits.append(seg_info.bit_position)
            elif was_active and not now_active:
                self._global_state &= ~segment_bit
                toggled_segment_bits.append(seg_info.bit_position)

        # Re-link only rules that require a toggled segment; their linkage is a
        # pure function of the (now updated) global state.
        if toggled_segment_bits:
            rules_to_recheck: set[int] = set()
            for bitpos in toggled_segment_bits:
                rules = self._segbit_to_rules.get(bitpos)
                if rules:
                    rules_to_recheck.update(rules)
            for rule_id in rules_to_recheck:
                link_info = self._rule_links[rule_id]
                if link_info.required_segment_mask == 0:
                    continue
                linked = (
                    self._global_state & link_info.required_segment_mask
                ) == link_info.required_segment_mask
                link_info.is_linked = linked
                if linked:
                    self._linked_rules.add(rule_id)
                else:
                    self._linked_rules.discard(rule_id)

        self._present_fields = new_fields
        return self._linked_rules - previously_linked

    def get_linked_rules(self) -> set[int]:
        """Return all currently linked rule IDs. O(1) lookup."""
        return set(self._linked_rules)

    def linked_rules_for(self, present_fields: frozenset[str] | set[str]) -> set[int]:
        """Pure, side-effect-free linkage query for a set of present field names.

        Computes exactly what ``update_facts(facts)`` followed by
        ``get_linked_rules()`` would return for a fact whose key set is
        ``present_fields`` - but **without mutating any instance state**
        (``_global_state``, per-segment ``current_state``, ``_linked_rules`` are
        all left untouched).

        This is the stateless / thread-safe entry point: multiple threads may
        call it concurrently on a single shared engine because it reads only the
        immutable registration structures (``_segment_bits`` / ``_rule_links``)
        built at load time and writes nothing back. The mutating
        :meth:`update_facts` / :meth:`update_facts_delta` remain for streaming
        mode, which is single-stream/owned by one thread by contract.

        Soundness: segment activation depends only on field *presence* (never on
        values), so a segment is active iff all its field names are in
        ``present_fields``; a rule is linked iff every required segment bit is on.

        Args:
            present_fields: the set of field names present in the fact.

        Returns:
            The set of rule IDs that are linked for that field-presence set.
        """
        # Compute the global segment-active mask from presence only. No writes.
        # NOTE: a segment with no fields (field_bits == {}) is active because
        # ``all(...)`` over an empty iterable is True - this matches
        # ``update_facts`` where ``current_state (0) == field_mask (0)``.
        global_state = 0
        for seg_info in self._segment_bits.values():
            if all(f in present_fields for f in seg_info.field_bits):
                global_state |= 1 << seg_info.bit_position

        linked: set[int] = set()
        for rule_id, link_info in self._rule_links.items():
            mask = link_info.required_segment_mask
            if mask and (global_state & mask) == mask:
                linked.add(rule_id)
        return linked

    def linked_subset_for(
        self,
        present_fields: frozenset[str] | set[str],
        candidate_ids: list[int] | set[int] | frozenset[int],
    ) -> list[int]:
        """Presence-narrow a pre-selected candidate set (pure, side-effect-free).

        Like :meth:`linked_rules_for`, but instead of scanning *every* registered
        rule it only checks the ``candidate_ids`` handed in (e.g. the survivors of
        the value-aware alpha pre-filter). This is the secondary, presence-only
        narrow in the P1.1 pipeline: once the alpha layer - the **primary**
        reducer - has cut the universe to a small survivor set, confirming
        field-presence for just those survivors is ``O(segments + |candidates|)``
        instead of ``O(all rules)``.

        Soundness is identical to :meth:`linked_rules_for`: a segment is active
        iff all its field names are present; a rule is linked iff every required
        segment bit is on. Rules whose ``required_segment_mask`` is 0 (no
        registered segment) are never linked, matching the mutating path.

        Args:
            present_fields: the set of field names present in the fact.
            candidate_ids: the rule ids to test (order preserved in the result
                when a list is passed).

        Returns:
            The subset of ``candidate_ids`` that are linked for that presence set.
        """
        # Compute the global segment-active mask once from presence only.
        global_state = 0
        for seg_info in self._segment_bits.values():
            if all(f in present_fields for f in seg_info.field_bits):
                global_state |= 1 << seg_info.bit_position

        rule_links = self._rule_links
        out: list[int] = []
        for rid in candidate_ids:
            link = rule_links.get(rid)
            if link is None:
                continue
            mask = link.required_segment_mask
            if mask and (global_state & mask) == mask:
                out.append(rid)
        return out

    def is_rule_linked(self, rule_id: int) -> bool:
        """Check if a specific rule is linked. O(1)."""
        link = self._rule_links.get(rule_id)
        return link.is_linked if link else False

    def get_segment_state(self, segment_id: str) -> int:
        """Get the current state bits for a segment."""
        seg = self._segment_bits.get(segment_id)
        return seg.current_state if seg else 0

    def clear(self) -> None:
        """Clear all registrations and state."""
        self._segment_bits.clear()
        self._rule_links.clear()
        self._global_state = 0
        self._next_segment_bit = 0
        self._linked_rules.clear()
        self._field_to_segments.clear()
        self._segbit_to_rules.clear()
        self._present_fields = set()
        self._has_baseline = False
