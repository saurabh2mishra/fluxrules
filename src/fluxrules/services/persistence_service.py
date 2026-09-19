"""Persistence service - solely responsible for rule persistence."""

from __future__ import annotations

from fluxrules.domain.models import EngineRule, Ruleset
from fluxrules.ports.persistence import RulePersistencePort


class PersistenceService:
    """Manages rule persistence through a :class:`RulePersistencePort`.

    Single responsibility: save, load, and delete rules from storage.

    Construct directly with a port instance, or use the convenience
    factory :meth:`create_default` which pulls the adapter from the
    DI :class:`~fluxrules.di.ServiceFactory`.

    Example::

        service = PersistenceService.create_default()
        rule_id = service.save_rule(rule)
    """

    def __init__(self, persistence_adapter: RulePersistencePort) -> None:
        self._persistence = persistence_adapter

    @classmethod
    def create_default(cls) -> PersistenceService:
        """Create a service backed by the DI-managed persistence adapter.

        Uses :meth:`ServiceFactory.create_persistence_adapter` so the
        concrete backend (in-memory, PostgreSQL, …) is determined by
        the active :class:`~fluxrules.config.RuntimeConfig`.
        """
        from fluxrules.di import ServiceFactory

        return cls(ServiceFactory.create_persistence_adapter())

    # ── Delegate methods ─────────────────────────────────────────────────────

    def save_rule(self, rule: EngineRule, group: str = "", created_by: int | None = None) -> int:
        """Persist a rule."""
        return self._persistence.save_rule(rule, group=group, created_by=created_by)

    def load_rule(self, rule_id: int) -> EngineRule | None:
        """Load a rule by ID."""
        return self._persistence.load_rule(rule_id)

    def load_all_rules(self) -> list[EngineRule]:
        """Load all persisted rules."""
        return self._persistence.load_all_rules()

    def delete_rule(self, rule_id: int) -> bool:
        """Delete a rule."""
        return self._persistence.delete_rule(rule_id)

    def save_ruleset(self, ruleset: Ruleset, created_by: int | None = None) -> list[int]:
        """Persist all rules in a ruleset."""
        return self._persistence.save_ruleset(ruleset, created_by=created_by)

    def load_ruleset(self, group: str) -> Ruleset:
        """Load a ruleset by group name."""
        return self._persistence.load_ruleset(group)

    def load_all_rulesets(self) -> dict[str, Ruleset]:
        """Load all rulesets."""
        return self._persistence.load_all_rulesets()
