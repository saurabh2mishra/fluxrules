"""Database-backed ruleset repository using a persistence adapter.

Delegates storage operations to the injected
:class:`~fluxrules.ports.persistence.RulePersistencePort`, allowing
the repository layer to remain independent of any particular ORM or
database technology.
"""

from __future__ import annotations

import logging

from fluxrules.domain.models import Ruleset
from fluxrules.ports.persistence import RulePersistencePort
from fluxrules.ports.repository import RulesetRepositoryPort

logger = logging.getLogger(__name__)


class DatabaseRulesetRepository(RulesetRepositoryPort):
    """Ruleset repository backed by a :class:`RulePersistencePort`.

    All database interaction is delegated to *persistence*, keeping
    this class free of ORM or SQL coupling.

    Args:
        persistence: The persistence adapter used for read/write
            operations on rules.
    """

    def __init__(self, persistence: RulePersistencePort) -> None:
        self._persistence = persistence

    def save(self, ruleset: Ruleset) -> Ruleset:
        """Persist every rule in *ruleset* and return it."""
        self._persistence.save_ruleset(ruleset)
        return ruleset

    def get(self, ruleset_id: int | str) -> Ruleset | None:
        """Load a ruleset by its group name (or numeric id as string)."""
        group = str(ruleset_id)
        ruleset = self._persistence.load_ruleset(group)
        if not ruleset.rules:
            return None
        return ruleset

    def list_all(self) -> list[Ruleset]:
        """Return all rulesets grouped by their group name."""
        return list(self._persistence.load_all_rulesets().values())

    def delete(self, ruleset_id: int | str) -> bool:
        """Delete all rules belonging to the given ruleset."""
        group = str(ruleset_id)
        ruleset = self._persistence.load_ruleset(group)
        if not ruleset.rules:
            return False
        for rule in ruleset.rules:
            self._persistence.delete_rule(rule.id)
        return True
