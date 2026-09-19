"""Typed schema definitions for FluxRules.

Provides validated dataclasses for major data structures,
enabling type-safe processing and IDE auto-complete support.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class RuleDefinition:
    """Validated rule definition.

    Attributes:
        id: Unique rule identifier.
        name: Human-readable rule name.
        conditions: List of condition patterns.
        actions: List of actions to execute.
        priority: Execution priority (higher = earlier), defaults to 100.
    """

    id: str
    name: str
    conditions: list[dict[str, Any]]
    actions: list[dict[str, Any]]
    priority: int = 100

    def __post_init__(self) -> None:
        """Validate rule structure after initialisation."""
        if not self.id:
            raise ValueError("Rule ID cannot be empty")
        if not self.conditions:
            raise ValueError("Rule must have at least one condition")
        if not self.actions:
            raise ValueError("Rule must have at least one action")


@dataclass
class EvaluationContext:
    """Context passed through a single evaluation cycle.

    Attributes:
        facts: The fact dictionary under evaluation.
        trace: Collected trace entries (populated during evaluation).
        metadata: Arbitrary caller-supplied metadata.
    """

    facts: dict[str, Any]
    trace: list[dict[str, Any]] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class AccumulateConfig:
    """Configuration for an accumulate node.

    Attributes:
        function: Aggregation function name (``sum``, ``count``, ``avg``, etc.).
        field: Fact field to aggregate over.
        constraint: Optional filter expression.
        result_binding: Variable name for the aggregation result.
    """

    function: str
    field: str
    constraint: str | None = None
    result_binding: str = "result"


@dataclass
class EngineConfig:
    """Configuration for engine instantiation.

    Attributes:
        engine_type: The engine identifier (``PHREAK``).
        ttl_seconds: Rule TTL for cache invalidation (0 = unlimited).
        max_rules: Hard limit on loaded rules (0 = unlimited).
        enable_metrics: Whether to collect runtime metrics.
    """

    engine_type: str = "PHREAK"
    ttl_seconds: int = 0
    max_rules: int = 0
    enable_metrics: bool = False
