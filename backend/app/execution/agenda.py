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

    def __len__(self) -> int:
        return len(self._heap)
