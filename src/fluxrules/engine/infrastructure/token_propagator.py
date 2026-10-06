"""Token propagator for implicit rule discovery."""

from __future__ import annotations

import logging
from typing import Any

from fluxrules.engine.infrastructure.segment_network import SegmentNetwork
from fluxrules.engine.infrastructure.working_memory import UnifiedWorkingMemory

logger = logging.getLogger(__name__)


class TokenPropagator:
    """Propagate facts through the segment network to discover matching rules.

    This is the heart of implicit discovery: given a fact, find which
    rules' condition fields overlap with the fact's fields.
    """

    def __init__(
        self,
        segment_network: SegmentNetwork,
        working_memory: UnifiedWorkingMemory,
    ) -> None:
        self._segment_network = segment_network
        self._working_memory = working_memory
        self._visited: set[str] = set()  # loop detection

    def propagate(self, facts: dict[str, Any], affected_segments: set[str]) -> list[int]:
        """Propagate a fact through affected segments.

        Returns the rule IDs that are *candidates* for this fact: those whose
        segments' fields are all present. Field presence is not a match - the
        conditions still have to be evaluated - so this is a prefilter, which
        is why the result feeds ``candidate_rule_ids`` and never
        ``fired_rules``.
        """
        candidate_rule_ids: list[int] = []
        fact_fields = set(facts.keys())
        fact_field_count = len(fact_fields)

        for seg in self._segment_network.segments.values():
            if seg.segment_id not in affected_segments:
                continue
            # FAST REJECT: segment needing more fields than fact has
            # cannot possibly be a subset - skip without set comparison
            if len(seg.fields) > fact_field_count:
                continue
            # A rule matches at the segment level if the segment's fields
            # are a subset of the fact's fields
            if seg.fields <= fact_fields:
                candidate_rule_ids.extend(seg.rule_ids)

        # Deduplicate while preserving order
        seen: set[int] = set()
        unique: list[int] = []
        for rid in candidate_rule_ids:
            if rid not in seen:
                seen.add(rid)
                unique.append(rid)
        return unique
