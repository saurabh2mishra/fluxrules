from __future__ import annotations

import heapq
from typing import List, Tuple
from dataclasses import dataclass, field


@dataclass
class Activation:
    rule_id: str
    priority: int
    matched_facts: List[dict] = field(default_factory=list)
    specificity: int = 0
    recency: int = 0


class Agenda:
    """Priority queue for activations: priority > recency > specificity."""

    def __init__(self):
        self._heap: List[Tuple[int, int, int, Activation]] = []

    def push(self, activation: Activation) -> None:
        key = (-activation.priority, -activation.recency, -activation.specificity, activation)
        heapq.heappush(self._heap, key)

    def pop(self) -> Activation | None:
        if not self._heap:
            return None
        return heapq.heappop(self._heap)[-1]

    def retract_fact_activations(self, fact_id: str) -> int:
        """Remove queued activations that depend on a retracted fact."""
        before = len(self._heap)
        self._heap = [
            item
            for item in self._heap
            if not any(fact.get("fact_id") == fact_id for fact in item[-1].matched_facts)
        ]
        heapq.heapify(self._heap)
        return before - len(self._heap)

    def clear(self) -> None:
        self._heap.clear()

    def __len__(self) -> int:
        return len(self._heap)
