"""Agenda and conflict resolution for unified engine."""

from __future__ import annotations

import heapq
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass(order=False)
class Activation:
    """A rule activation pending in the agenda."""

    rule_id: int
    fact_ids: list[str] = field(default_factory=list)
    priority: int = 0
    timestamp: float = field(default_factory=time.time)

    def __lt__(self, other: Activation) -> bool:
        # Higher priority first, then earlier timestamp (FIFO within same priority)
        if self.priority != other.priority:
            return self.priority > other.priority
        return self.timestamp < other.timestamp


class ConflictResolutionStrategy(ABC):
    """Interface for conflict resolution strategies."""

    @abstractmethod
    def sort_key(self, activation: Activation) -> Any:
        """Return a sort key; lower key = fires first."""
        ...


class SalienceRecencyStrategy(ConflictResolutionStrategy):
    """Default strategy: highest priority first, then most recent."""

    def sort_key(self, activation: Activation) -> tuple[int, float]:
        return (-activation.priority, -activation.timestamp)


class Agenda:
    """Priority queue of rule activations (Drools Agenda pattern).

    Supports activation cancellation (unscheduling) for dirty tracking.
    When facts change, rules that depend on those facts can be cancelled
    before they are fired.
    """

    def __init__(self) -> None:
        self._heap: list[tuple[Any, int, Activation]] = []
        self._strategy: ConflictResolutionStrategy = SalienceRecencyStrategy()
        self._counter = 0  # tiebreaker for heap stability
        self._cancelled: set[int] = set()  # cancelled rule IDs

    def set_strategy(self, strategy: ConflictResolutionStrategy) -> None:
        self._strategy = strategy

    def add_activation(
        self, rule_id: int, fact_ids: list[str] | None = None, priority: int = 0
    ) -> None:
        """Add a rule activation to the agenda."""
        act = Activation(
            rule_id=rule_id,
            fact_ids=fact_ids or [],
            priority=priority,
        )
        key = self._strategy.sort_key(act)
        self._counter += 1
        # Negate the counter so insertion order acts as a *recency* tiebreaker
        # (most recently added fires first) consistent with
        # SalienceRecencyStrategy. This makes ordering deterministic even when
        # time.time() returns identical timestamps for activations added in
        # quick succession (its resolution is coarser than insertion speed).
        heapq.heappush(self._heap, (key, -self._counter, act))

    def cancel_activation(self, rule_id: int) -> None:
        """Cancel a pending activation.

        When a rule's inputs change, this method removes it from the
        agenda without firing it. The next evaluation will re-check
        if it should be activated.

        Args:
            rule_id: ID of the rule to cancel
        """
        self._cancelled.add(rule_id)

    def next_activation(self) -> Activation | None:
        """Pop the next non-cancelled activation.

        Now returns None if all remaining activations are cancelled.
        """
        while self._heap:
            _, _, act = heapq.heappop(self._heap)
            if act.rule_id not in self._cancelled:
                return act
        return None

    def is_empty(self) -> bool:
        return len(self._heap) == 0

    def clear(self) -> None:
        self._heap.clear()
        self._counter = 0
        self._cancelled.clear()

    def __len__(self) -> int:
        return len(self._heap)
