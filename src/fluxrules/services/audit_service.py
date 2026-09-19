"""Audit service - solely responsible for execution audit trail."""

from __future__ import annotations

from fluxrules.domain.models import EvaluationResult
from fluxrules.ports.execution_store import ExecutionStorePort


class AuditService:
    """Records and retrieves evaluation execution results.

    Single responsibility: manage the audit trail without concern
    for evaluation logic or persistence details.
    """

    def __init__(self, store: ExecutionStorePort) -> None:
        self.store = store

    def record_evaluation(self, result: EvaluationResult) -> None:
        """Record an evaluation result for audit purposes."""
        self.store.save(result)

    def get_execution(self, execution_id: str) -> EvaluationResult | None:
        """Retrieve a recorded execution by ID."""
        return self.store.get(execution_id)

    def delete_execution(self, execution_id: str) -> bool:
        """Delete a recorded execution."""
        return self.store.delete(execution_id)
