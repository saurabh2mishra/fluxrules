"""High-level repository for persisting and loading rules to/from the database."""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from fluxrules.domain.models import EngineRule, Ruleset
from fluxrules.persistence.mappers import domain_rule_to_orm, orm_rule_to_domain

logger = logging.getLogger("fluxrules.persistence")


class RuleRepository:
    """Database-backed repository for :class:`Rule` domain objects.

    Usage::

        from fluxrules.api.database import SessionLocal
        repo = RuleRepository(SessionLocal())
        rule_id = repo.save_rule(my_rule)
        loaded = repo.load_rule(rule_id)
    """

    def __init__(self, db: Session) -> None:
        self.db = db

    # Save

    def save_rule(self, rule: EngineRule, group: str = "", created_by: int | None = None) -> int:
        """Persist a domain Rule to the database. Returns the database ID."""

        orm_rule = domain_rule_to_orm(rule, group=group, created_by=created_by)
        self.db.add(orm_rule)
        self.db.commit()
        self.db.refresh(orm_rule)
        return orm_rule.id

    def save_ruleset(self, ruleset: Ruleset, created_by: int | None = None) -> list[int]:
        """Persist all rules in a Ruleset. Returns list of database IDs."""
        ids: list[int] = []
        for rule in ruleset.rules:
            rid = self.save_rule(rule, group=ruleset.group, created_by=created_by)
            ids.append(rid)
        return ids

    # Load

    def load_rule(self, rule_id: int) -> EngineRule | None:
        """Load a single Rule by database ID."""
        from fluxrules.api.models.rule import Rule as OrmRule

        orm_rule = self.db.query(OrmRule).filter(OrmRule.id == rule_id).first()
        if orm_rule is None:
            return None
        return orm_rule_to_domain(orm_rule)

    def load_rules_by_group(self, group: str) -> list[EngineRule]:
        """Load all rules belonging to *group*."""
        from fluxrules.api.models.rule import Rule as OrmRule

        orm_rules = (
            self.db.query(OrmRule)
            .filter(OrmRule.group == group)
            .order_by(OrmRule.priority.desc())
            .all()
        )
        return [orm_rule_to_domain(r) for r in orm_rules]

    def load_all_rules(self) -> list[EngineRule]:
        """Load every rule from the database."""
        from fluxrules.api.models.rule import Rule as OrmRule

        orm_rules = self.db.query(OrmRule).order_by(OrmRule.priority.desc()).all()
        return [orm_rule_to_domain(r) for r in orm_rules]

    def load_ruleset(self, group: str) -> Ruleset:
        """Load all rules in *group* as a :class:`Ruleset`."""
        rules = self.load_rules_by_group(group)
        return Ruleset(group=group, rules=tuple(rules))

    def load_all_rulesets(self) -> dict[str, Ruleset]:
        """Load all rules grouped into Rulesets by group name."""
        all_rules = self.load_all_rules()
        groups: dict[str, list[EngineRule]] = {}
        for r in all_rules:
            g = r.group or ""
            groups.setdefault(g, []).append(r)
        return {g: Ruleset(group=g, rules=tuple(rs)) for g, rs in groups.items()}

    # Update / Delete

    def update_rule(self, rule_id: int, **kwargs) -> EngineRule | None:
        """Update specific fields of a rule. Returns updated domain Rule or None."""
        from fluxrules.api.models.rule import Rule as OrmRule

        orm_rule = self.db.query(OrmRule).filter(OrmRule.id == rule_id).first()
        if orm_rule is None:
            return None

        for key, value in kwargs.items():
            if key == "conditions" and isinstance(value, (list, tuple)):
                # Store a DSL tree, not a list of condition dicts: the column
                # holds exactly one shape.
                from fluxrules.domain.dsl.evaluator import conditions_to_dsl

                orm_rule.condition_dsl = conditions_to_dsl(value)
            elif key == "condition_dsl":
                orm_rule.condition_dsl = value
            elif key == "actions" and isinstance(value, (list, tuple)):
                orm_rule.action = "\n".join(value)
            elif hasattr(orm_rule, key):
                setattr(orm_rule, key, value)

        orm_rule.updated_at = datetime.now(timezone.utc)
        self.db.commit()
        self.db.refresh(orm_rule)
        return orm_rule_to_domain(orm_rule)

    def delete_rule(self, rule_id: int) -> bool:
        """Delete a rule by ID. Returns True if deleted."""
        from fluxrules.api.models.rule import Rule as OrmRule

        orm_rule = self.db.query(OrmRule).filter(OrmRule.id == rule_id).first()
        if orm_rule is None:
            return False
        self.db.delete(orm_rule)
        self.db.commit()
        return True
