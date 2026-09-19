"""Port interface for ruleset repository."""

from __future__ import annotations

from abc import ABC, abstractmethod

from fluxrules.domain.models import Ruleset


class RulesetRepositoryPort(ABC):
    """Abstract interface for ruleset storage and retrieval."""

    @abstractmethod
    def save(self, ruleset: Ruleset) -> Ruleset:
        """Save or update a ruleset. Return the saved ruleset."""

    @abstractmethod
    def get(self, ruleset_id: int | str) -> Ruleset | None:
        """Retrieve a ruleset by ID."""

    @abstractmethod
    def list_all(self) -> list[Ruleset]:
        """List all stored rulesets."""

    @abstractmethod
    def delete(self, ruleset_id: int | str) -> bool:
        """Delete a ruleset. Return True if found and deleted."""
