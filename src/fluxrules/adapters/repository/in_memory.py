from __future__ import annotations

from fluxrules.domain.models import EvaluationResult, Ruleset


class InMemoryRulesetRepository:
    def __init__(self):
        self._items: dict[str, Ruleset] = {}

    def save(self, ruleset: Ruleset) -> None:
        self._items[ruleset.id] = ruleset

    def get(self, ruleset_id: str) -> Ruleset | None:
        return self._items.get(ruleset_id)


class InMemoryExecutionStore:
    def __init__(self):
        self._items: dict[str, EvaluationResult] = {}

    def save(self, result: EvaluationResult) -> None:
        self._items[result.execution_id] = result

    def get(self, execution_id: str) -> EvaluationResult | None:
        return self._items.get(execution_id)
