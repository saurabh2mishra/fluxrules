from __future__ import annotations

from typing import List

from app.execution.agenda import Agenda
from app.rete.rete_nodes import Activation


class RuleScheduler:
    def __init__(self):
        self._agenda = Agenda()
        self._sequence = 0

    def add_activation(self, rule_id: str, priority: int, specificity: int, matched_facts: List[dict]) -> None:
        self._sequence += 1
        self._agenda.push(
            Activation(
                rule_id=rule_id,
                priority=priority,
                specificity=specificity,
                recency=self._sequence,
                matched_facts=matched_facts,
            )
        )

    def next_activation(self) -> Activation | None:
        return self._agenda.pop()
