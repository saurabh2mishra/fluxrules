"""Port interface for rule persistence (database-backed storage)."""

from __future__ import annotations

from abc import ABC, abstractmethod

from fluxrules.domain.models import EngineRule, Ruleset


class RulePersistencePort(ABC):
    """Abstract interface for rule persistence.

    Decouples the core engine and services from concrete database
    implementations (SQLAlchemy, file-based, etc.).
    """

    @abstractmethod
    def save_rule(self, rule: EngineRule, group: str = "", created_by: int | None = None) -> int:
        """Persist a rule; return database ID."""

    @abstractmethod
    def load_rule(self, rule_id: int) -> EngineRule | None:
        """Retrieve a rule by ID."""

    @abstractmethod
    def load_all_rules(self) -> list[EngineRule]:
        """Load all rules from storage."""

    @abstractmethod
    def delete_rule(self, rule_id: int) -> bool:
        """Delete a rule."""

    @abstractmethod
    def save_ruleset(self, ruleset: Ruleset, created_by: int | None = None) -> list[int]:
        """Persist all rules in a Ruleset. Returns list of database IDs."""

    @abstractmethod
    def load_ruleset(self, group: str) -> Ruleset:
        """Load all rules in a group as a Ruleset."""

    @abstractmethod
    def load_all_rulesets(self) -> dict[str, Ruleset]:
        """Load all rules grouped into Rulesets by group name."""

    @abstractmethod
    def update_rule(self, rule_id: int, **kwargs) -> EngineRule | None:
        """Update specific fields of a rule. Returns updated domain Rule or None."""


class InMemoryRulePersistence(RulePersistencePort):
    """In-memory implementation of RulePersistencePort for testing and standalone use."""

    def __init__(self) -> None:
        self._rules: dict[int, EngineRule] = {}
        self._next_id = 1

    def save_rule(self, rule: EngineRule, group: str = "", created_by: int | None = None) -> int:
        rid = self._next_id
        self._next_id += 1
        self._rules[rid] = rule
        return rid

    def load_rule(self, rule_id: int) -> EngineRule | None:
        return self._rules.get(rule_id)

    def load_all_rules(self) -> list[EngineRule]:
        return list(self._rules.values())

    def delete_rule(self, rule_id: int) -> bool:
        if rule_id in self._rules:
            del self._rules[rule_id]
            return True
        return False

    def save_ruleset(self, ruleset: Ruleset, created_by: int | None = None) -> list[int]:
        ids = []
        for rule in ruleset.rules:
            rid = self.save_rule(rule, group=ruleset.group, created_by=created_by)
            ids.append(rid)
        return ids

    def load_ruleset(self, group: str) -> Ruleset:
        rules = [r for r in self._rules.values() if r.group == group]
        return Ruleset(group=group, rules=tuple(rules))

    def load_all_rulesets(self) -> dict[str, Ruleset]:
        groups: dict[str, list[EngineRule]] = {}
        for r in self._rules.values():
            g = r.group or ""
            groups.setdefault(g, []).append(r)
        return {g: Ruleset(group=g, rules=tuple(rs)) for g, rs in groups.items()}

    def update_rule(self, rule_id: int, **kwargs) -> EngineRule | None:
        if rule_id not in self._rules:
            return None
        # For in-memory, just return the existing rule (frozen dataclass)
        return self._rules[rule_id]
