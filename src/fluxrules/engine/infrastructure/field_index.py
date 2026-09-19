"""Field index for global field-to-segment mapping (dirty tracking)."""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


class FieldIndex:
    """Maps field names to segment IDs for fast dirty-tracking.

    When a fact arrives with fields ``{amount, country}``, the field index
    returns which segments reference those fields, so only affected
    segments need re-evaluation.
    """

    def __init__(self) -> None:
        self._field_to_segments: dict[str, set[str]] = {}
        self._field_to_rules: dict[str, set[int]] = {}

    @property
    def fields(self) -> dict[str, set[str]]:
        return self._field_to_segments

    def register(self, field_name: str, segment_id: str) -> None:
        """Register a field → segment mapping."""
        self._field_to_segments.setdefault(field_name, set()).add(segment_id)

    def register_rule(self, field_name: str, rule_id: int) -> None:
        """Register a field → rule mapping."""
        self._field_to_rules.setdefault(field_name, set()).add(rule_id)

    def get_affected_segments(self, fact: dict[str, Any]) -> set[str]:
        """Return segment IDs affected by the fact's fields."""
        affected: set[str] = set()
        for field_name in fact:
            affected.update(self._field_to_segments.get(field_name, set()))
        return affected

    def get_affected_rules(self, fact: dict[str, Any]) -> set[int]:
        """Return rule IDs whose conditions reference any field in the fact."""
        affected: set[int] = set()
        for field_name in fact:
            affected.update(self._field_to_rules.get(field_name, set()))
        return affected

    def build_from_rules(self, rules: list[Any]) -> None:
        """Build field index from a list of Rule objects.

        Uses the same segment naming as SegmentNetwork so that
        ``get_affected_segments`` returns IDs the propagator recognises.
        """
        from fluxrules.domain.unified_rule import Rule as CanonicalRule
        from fluxrules.engine.infrastructure.global_rule_repository import (
            normalize_rule,
        )
        from fluxrules.engine.infrastructure.segment_network import _extract_fields

        for rule in rules:
            # Normalise on *type*, not on attribute presence: see the matching
            # note in SegmentNetwork.add_rules.
            if not isinstance(rule, CanonicalRule):
                rule = normalize_rule(rule)

            if rule.id is None:
                raise ValueError("Rule must have an id before field indexing")
            rule_id = rule.id

            fields = _extract_fields(rule.condition_dsl)
            if fields:
                segment_id = f"seg_{'_'.join(sorted(fields))}"
            else:
                segment_id = f"seg_{rule_id}"
            for f in fields:
                self.register(f, segment_id)
                self.register_rule(f, rule_id)

    def clear(self) -> None:
        self._field_to_segments.clear()
        self._field_to_rules.clear()

    def __len__(self) -> int:
        return len(self._field_to_segments)
