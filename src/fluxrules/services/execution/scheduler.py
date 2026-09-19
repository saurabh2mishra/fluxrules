from __future__ import annotations

from typing import Any

from fluxrules.services.execution.agenda import Activation, Agenda


class RuleScheduler:
    def __init__(self):
        self._agenda = Agenda()
        self._sequence = 0

    def add_activation(
        self, rule_id: str, priority: int, specificity: int, matched_facts: list[dict]
    ) -> None:
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

    def add_candidate(self, candidate: dict[str, Any]) -> None:
        """Accept activation-candidate dictionaries from evaluator layers."""
        self.add_activation(
            rule_id=str(candidate["rule_id"]),
            priority=int(candidate.get("priority", 0)),
            specificity=int(candidate.get("specificity", 0)),
            matched_facts=candidate.get("matched_facts", []),
        )
