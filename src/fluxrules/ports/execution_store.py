"""Port interface for execution result storage."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class ExecutionStorePort(ABC):
    """Abstract interface for persisting execution results."""

    @abstractmethod
    def save(self, result: Any) -> None:
        """Save an execution result."""

    @abstractmethod
    def get(self, execution_id: str) -> Any | None:
        """Retrieve a stored execution result by execution ID."""

    @abstractmethod
    def delete(self, execution_id: str) -> bool:
        """Delete a stored execution result. Return True if found and deleted."""
