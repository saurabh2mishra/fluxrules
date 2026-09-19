"""In-memory implementations of repository and execution store ports."""

from __future__ import annotations

from typing import Any

from fluxrules.domain.models import Ruleset
from fluxrules.ports.execution_store import ExecutionStorePort
from fluxrules.ports.repository import RulesetRepositoryPort


class InMemoryExecutionStore(ExecutionStorePort):
    """Simple in-memory execution result storage."""

    def __init__(self) -> None:
        """Initialize the in-memory store."""
        self._store: dict[str, Any] = {}

    def save(self, result: Any) -> None:
        """Save an execution result keyed by its execution_id."""
        self._store[result.execution_id] = result

    def get(self, execution_id: str) -> Any | None:
        """Retrieve a stored execution result."""
        return self._store.get(execution_id)

    def delete(self, execution_id: str) -> bool:
        """Delete a stored execution result."""
        if execution_id in self._store:
            del self._store[execution_id]
            return True
        return False


class InMemoryRulesetRepository(RulesetRepositoryPort):
    """Simple in-memory ruleset storage."""

    def __init__(self) -> None:
        """Initialize the in-memory repository."""
        self._store: dict[str, Ruleset] = {}

    def save(self, ruleset: Ruleset) -> Ruleset:
        """Save or update a ruleset."""
        self._store[ruleset.group] = ruleset
        return ruleset

    def get(self, ruleset_id: int | str) -> Ruleset | None:
        """Retrieve a ruleset by group name."""
        return self._store.get(str(ruleset_id))

    def list_all(self) -> list[Ruleset]:
        """List all stored rulesets."""
        return list(self._store.values())

    def delete(self, ruleset_id: int | str) -> bool:
        """Delete a ruleset."""
        if ruleset_id in self._store:
            del self._store[ruleset_id]
            return True
        return False
