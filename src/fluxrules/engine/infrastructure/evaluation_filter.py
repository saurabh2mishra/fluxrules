"""Evaluation filter for domain/tag-based rule filtering."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class EvaluationFilter:
    """Optional filtering for unified engine evaluation.

    When provided to ``evaluate()``, only rules matching these criteria
    are considered. All criteria are AND-combined: a rule must match
    *every* non-None filter field.

    Attributes:
        domains: Only evaluate rules in these domains.
        tags: Only evaluate rules having at least one of these tags.
        min_priority: Minimum rule priority (inclusive).
        max_priority: Maximum rule priority (inclusive).
    """

    domains: frozenset[str] | None = None
    tags: frozenset[str] | None = None
    min_priority: int | None = None
    max_priority: int | None = None
