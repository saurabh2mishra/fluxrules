from __future__ import annotations

from typing import Protocol

from fluxrules.domain.models import EvaluationResult


class ExecutionStorePort(Protocol):
    def save(self, result: EvaluationResult) -> None: ...

    def get(self, execution_id: str) -> EvaluationResult | None: ...
