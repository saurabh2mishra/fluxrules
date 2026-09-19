"""Rule persistence manager for automatic database persistence.

Handles automatic persistence of rules to database without requiring
user intervention. Provides graceful degradation if database is unavailable.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from fluxrules.domain.models import EngineRule
from fluxrules.persistence.db_connection_manager import DBConnectionManager
from fluxrules.persistence.rule_repository import RuleRepository

if TYPE_CHECKING:
    from fluxrules.domain.unified_rule import Rule as CanonicalRule

logger = logging.getLogger(__name__)


class PersistenceManager:
    """Manages automatic rule persistence.

    Usage:
        # Persist a rule
        pm = PersistenceManager()
        persisted_rule = pm.persist_rule(rule)

        # Disable for testing
        pm.disable_persistence()

    Thread-safe and supports graceful fallback to in-memory mode.
    """

    def __init__(self, enabled: bool = True) -> None:
        """Initialize persistence manager.

        Args:
            enabled: Whether persistence is enabled (default: True)
        """
        self.enabled = enabled
        self._fallback_id_counter = 0
        logger.debug(f"PersistenceManager initialized (enabled={enabled})")

    def persist_rule(
        self,
        rule: EngineRule | CanonicalRule,
        group: str = "",
        created_by: int | None = None,
    ) -> EngineRule:
        """Persist a rule to database.

        Accepts either the canonical :class:`~fluxrules.domain.unified_rule.Rule`
        or the internal engine :class:`~fluxrules.domain.models.Rule`. A canonical
        rule is converted to the engine representation once, through its
        ``to_engine_rule`` adapter, so the rest of this method works with a single
        type.

        If persistence is disabled or fails, returns rule with locally-generated ID.

        Args:
            rule: Rule domain object to persist
            group: Optional group/category for the rule
            created_by: Optional user ID who created the rule

        Returns:
            Rule instance with database-assigned ID (or local ID if persistence disabled)

        Raises:
            ValueError: If rule has invalid data
        """
        from fluxrules.domain.unified_rule import Rule as CanonicalRule

        if isinstance(rule, CanonicalRule):
            rule = rule.to_engine_rule(group=group or None)

        if not self.enabled:
            # In-memory mode: generate local ID if not present
            if not rule.id:
                self._fallback_id_counter += 1
                # Create new rule instance with generated ID (for frozen dataclasses)
                rule = EngineRule(
                    id=self._fallback_id_counter,
                    name=rule.name,
                    actions=rule.actions,
                    priority=rule.priority,
                    group=group or rule.group,
                    description=rule.description,
                    enabled=rule.enabled,
                    created_at=rule.created_at,
                    updated_at=rule.updated_at,
                    condition_dsl=rule.condition_dsl,
                )
                logger.debug(
                    f"Persistence disabled - assigned local ID {rule.id} to rule: {rule.name}"
                )
            return rule

        try:
            session = DBConnectionManager.get_instance().get_session()
            repo = RuleRepository(session)

            # Save rule and get database ID
            db_id = repo.save_rule(rule, group=group, created_by=created_by)

            # Create new rule instance with database ID
            persisted_rule = EngineRule(
                id=db_id,
                name=rule.name,
                actions=rule.actions,
                priority=rule.priority,
                group=group or rule.group,
                description=rule.description,
                enabled=rule.enabled,
                created_at=rule.created_at,
                updated_at=rule.updated_at,
                # The authoritative condition tree carries through untouched.
                condition_dsl=rule.condition_dsl,
            )

            logger.info(f"Rule persisted successfully: {persisted_rule.name} (ID: {db_id})")
            session.close()
            return persisted_rule

        except Exception as e:
            # Handled, recoverable condition: we fall back to in-memory mode
            # below. Emitting a full traceback at ERROR made working code look
            # broken (e.g. "no such table: rules" on first run), so the detail
            # is kept at DEBUG for when it is actually being investigated.
            logger.debug(f"Failed to persist rule '{rule.name}': {e}", exc_info=True)

            # Graceful fallback: generate local ID and continue
            if not rule.id:
                self._fallback_id_counter += 1
                rule = EngineRule(
                    id=self._fallback_id_counter,
                    name=rule.name,
                    actions=rule.actions,
                    priority=rule.priority,
                    group=group or rule.group,
                    description=rule.description,
                    enabled=rule.enabled,
                    created_at=rule.created_at,
                    updated_at=rule.updated_at,
                    condition_dsl=rule.condition_dsl,
                )

            logger.info(
                f"No database configured; using in-memory mode. Rule has local ID: {rule.id}"
            )
            return rule

    def persist_ruleset(
        self,
        rules: list[EngineRule] | list[CanonicalRule],
        group: str = "",
        created_by: int | None = None,
    ) -> list[EngineRule]:
        """Persist multiple rules to database.

        Args:
            rules: Rule objects to persist (canonical or engine representation)
            group: Optional group/category for all rules
            created_by: Optional user ID who created the rules

        Returns:
            List of persisted rules with database-assigned IDs
        """
        persisted_rules = []
        for rule in rules:
            persisted = self.persist_rule(rule, group=group, created_by=created_by)
            persisted_rules.append(persisted)
        return persisted_rules

    def disable_persistence(self) -> None:
        """Disable persistence (useful for testing)."""
        self.enabled = False
        logger.info("Persistence disabled - switching to in-memory mode")

    def enable_persistence(self) -> None:
        """Enable persistence."""
        self.enabled = True
        logger.info("Persistence enabled")

    def is_enabled(self) -> bool:
        """Check if persistence is enabled.

        Returns:
            True if persistence is enabled, False otherwise
        """
        return self.enabled

    def __repr__(self) -> str:
        return f"PersistenceManager(enabled={self.enabled})"


# Global singleton instance
_persistence_manager: PersistenceManager | None = None


def get_persistence_manager() -> PersistenceManager:
    """Get or create the global persistence manager singleton.

    Returns:
        PersistenceManager instance
    """
    global _persistence_manager
    if _persistence_manager is None:
        _persistence_manager = PersistenceManager(enabled=True)
    return _persistence_manager


def set_persistence_manager(manager: PersistenceManager) -> None:
    """Set the global persistence manager (mainly for testing).

    Args:
        manager: PersistenceManager instance to use globally
    """
    global _persistence_manager
    _persistence_manager = manager
    logger.debug(f"Global persistence manager updated: {manager}")


def reset_persistence_manager() -> None:
    """Reset the global persistence manager to default."""
    global _persistence_manager
    _persistence_manager = PersistenceManager(enabled=True)
    logger.debug("Global persistence manager reset")
