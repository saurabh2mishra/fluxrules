"""Segment network for cross-domain segment sharing."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


def _extract_fields(condition_dsl: dict[str, Any]) -> set[str]:
    """Recursively extract field names from a condition DSL dict."""
    fields: set[str] = set()
    if not isinstance(condition_dsl, dict):
        return fields
    ctype = condition_dsl.get("type")
    if ctype == "condition":
        f = condition_dsl.get("field")
        if f:
            fields.add(f)
    elif ctype in ("composite", "group", "and", "or"):
        children = condition_dsl.get("conditions") or condition_dsl.get("children") or []
        for child in children:
            fields.update(_extract_fields(child))
    elif ctype == "not":
        inner = condition_dsl.get("condition")
        if inner:
            fields.update(_extract_fields(inner))
        for sub in condition_dsl.get("conditions", []):
            fields.update(_extract_fields(sub))
    elif ctype == "exists":
        f = condition_dsl.get("field")
        if f:
            fields.add(f)
        inner = condition_dsl.get("condition")
        if inner:
            fields.update(_extract_fields(inner))
    elif ctype == "accumulate":
        f = condition_dsl.get("field")
        if f:
            fields.add(f)
    return fields


@dataclass
class Segment:
    """A shared segment grouping rules with common condition fields.

    A segment is keyed by the set of condition ``fields`` its rules reference;
    every rule whose conditions touch exactly that field-set shares the segment.
    Segments are *flat* - there is no parent/child hierarchy. A prior design
    synthesized ``is_shared`` parent segments, but no rule was ever mapped to a
    parent, so the hierarchy did real work that changed nothing while costing an
    O(S^2) build at load. It was removed (PHREAK P2.1); the flat field-set
    grouping is the only path.
    """

    segment_id: str
    fields: frozenset[str]
    rule_ids: set[int] = field(default_factory=set)

    def matches_fields(self, fact_fields: set[str]) -> bool:
        """Check if this segment is affected by the given fact fields."""
        return bool(self.fields & fact_fields)


class SegmentNetwork:
    """Cross-domain segment network.

    Rules sharing the same condition fields are grouped into segments.
    This enables PHREAK-style lazy evaluation: only segments whose
    fields appear in the incoming fact are re-evaluated.
    """

    def __init__(self, max_rules: int = 50_000) -> None:
        self.max_rules = max_rules
        self._segments: dict[str, Segment] = {}
        self._rule_to_segments: dict[int, list[Segment]] = {}  # Direct Segment refs

    @property
    def segments(self) -> dict[str, Segment]:
        return self._segments

    def add_rules(self, rules: list[Any]) -> None:
        """Decompose rules into cross-domain segments."""
        from fluxrules.domain.unified_rule import Rule as CanonicalRule
        from fluxrules.engine.infrastructure.global_rule_repository import (
            normalize_rule,
        )

        for rule in rules:
            # Normalise dicts (and anything else rule-shaped) to canonical Rule.
            # The check is on *type*, not on the presence of a ``condition_dsl``
            # attribute: other rule shapes carry that attribute too, sometimes
            # unset, and duck-typing here let them through unnormalised with no
            # fields - so the rule got an empty segment and never fired.
            if not isinstance(rule, CanonicalRule):
                rule = normalize_rule(rule)

            if rule.id is None:
                raise ValueError("Rule must have an id before segment registration")
            rule_id = rule.id

            fields = _extract_fields(rule.condition_dsl)
            if not fields:
                # Rule with no condition fields gets its own segment
                seg_id = f"seg_{rule_id}"
                seg = Segment(segment_id=seg_id, fields=frozenset(), rule_ids={rule_id})
                self._segments[seg_id] = seg
                self._rule_to_segments[rule_id] = [seg]
                continue

            # Each rule gets a segment keyed by its field set
            seg_key = f"seg_{'_'.join(sorted(fields))}"
            if seg_key in self._segments:
                self._segments[seg_key].rule_ids.add(rule_id)
            else:
                self._segments[seg_key] = Segment(
                    segment_id=seg_key,
                    fields=frozenset(fields),
                    rule_ids={rule_id},
                )
            self._rule_to_segments.setdefault(rule_id, []).append(self._segments[seg_key])

    def get_affected_segments(self, fact_fields: set[str]) -> list[Segment]:
        """Return segments whose fields overlap with the fact's fields."""
        return [seg for seg in self._segments.values() if seg.matches_fields(fact_fields)]

    def get_segments_for_rule(self, rule_id: int) -> list[Segment]:
        """Return segments associated with a rule."""
        return self._rule_to_segments.get(rule_id, [])

    def clear(self) -> None:
        self._segments.clear()
        self._rule_to_segments.clear()

    def __len__(self) -> int:
        return len(self._segments)
