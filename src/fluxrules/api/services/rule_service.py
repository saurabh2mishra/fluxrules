import json
import logging
from collections.abc import Callable
from typing import Any

from sqlalchemy.orm import Session

from fluxrules.api.models.rule import Rule, RuleVersion
from fluxrules.api.schemas.rule import RuleCreate, RuleUpdate
from fluxrules.api.services.audit_service import AuditService

logger = logging.getLogger(__name__)

_invalidate_compiled_cache: Callable[[str | None], None] | None
try:
    from fluxrules.services.validation._compiled_cache import (
        invalidate as _invalidate_compiled_cache,
    )

    COMPILED_CACHE_AVAILABLE = True
except ImportError:
    _invalidate_compiled_cache = None
    COMPILED_CACHE_AVAILABLE = False


def invalidate_rule_cache(group: str | None = None):
    if _invalidate_compiled_cache is not None:
        _invalidate_compiled_cache(group)
        logger.debug(f"Compiled cache invalidated for group: {group or 'all'}")


class RuleService:
    def __init__(self, db: Session):
        self.db = db
        self.audit_service = AuditService(db)

    def list_rules(
        self,
        skip: int = 0,
        limit: int = 100,
        group: str | None = None,
        enabled: bool | None = None,
    ) -> list[Rule]:
        query = self.db.query(Rule)
        if group:
            query = query.filter(Rule.group == group)
        if enabled is not None:
            query = query.filter(Rule.enabled == enabled)
        return query.offset(skip).limit(limit).all()

    def get_rule(self, rule_id: int) -> Rule | None:
        return self.db.query(Rule).filter(Rule.id == rule_id).first()

    def create_rule(self, rule_data: RuleCreate, user_id: int) -> Rule:
        rule = Rule(
            name=rule_data.name,
            description=rule_data.description,
            group=rule_data.group,
            priority=rule_data.priority,
            enabled=rule_data.enabled,
            condition_dsl=rule_data.condition_dsl,
            action=rule_data.action,
            rule_metadata=rule_data.rule_metadata,
            evaluation_mode=rule_data.evaluation_mode,
            created_by=user_id,
            current_version=1,
        )
        self.db.add(rule)
        self.db.flush()

        self._create_version(rule, user_id, auto_commit=False)
        self.audit_service.log_action(
            "create", "rule", rule.id, user_id, "Rule created", auto_commit=False
        )

        self.db.commit()
        self.db.refresh(rule)

        invalidate_rule_cache(rule_data.group)

        return rule

    def update_rule(self, rule_id: int, rule_data: RuleUpdate, user_id: int) -> Rule | None:
        rule = self.get_rule(rule_id)
        if not rule:
            return None

        old_group = rule.group

        # Both condition_dsl and rule_metadata are JSON columns on `rules`:
        # SQLAlchemy serialises them, so pre-encoding here would store a JSON
        # string containing JSON.
        update_data = rule_data.model_dump(exclude_unset=True)

        for field, value in update_data.items():
            setattr(rule, field, value)

        rule.current_version += 1
        self.db.commit()
        self.db.refresh(rule)

        self._create_version(rule, user_id)
        self.audit_service.log_action("update", "rule", rule.id, user_id, "Rule updated")

        invalidate_rule_cache(old_group)
        if rule.group != old_group:
            invalidate_rule_cache(rule.group)

        return rule

    def delete_rule(self, rule_id: int) -> bool:
        rule = self.get_rule(rule_id)
        if not rule:
            return False

        group = rule.group

        self.db.delete(rule)
        self.db.commit()
        self.audit_service.log_action("delete", "rule", rule_id, None, "Rule deleted")

        invalidate_rule_cache(group)

        return True

    def _create_version(self, rule: Rule, user_id: int, auto_commit: bool = True):
        # rules.condition_dsl and rules.rule_metadata are JSON columns holding
        # dicts; the rule_versions equivalents are Text, so the snapshot is
        # serialised as it crosses that boundary.
        version = RuleVersion(
            rule_id=rule.id,
            version=rule.current_version,
            name=rule.name,
            description=rule.description,
            group=rule.group,
            priority=rule.priority,
            enabled=rule.enabled,
            condition_dsl=json.dumps(rule.condition_dsl)
            if not isinstance(rule.condition_dsl, str)
            else rule.condition_dsl,
            action=rule.action,
            rule_metadata=json.dumps(rule.rule_metadata)
            if rule.rule_metadata is not None and not isinstance(rule.rule_metadata, str)
            else rule.rule_metadata,
            created_by=user_id,
        )
        self.db.add(version)
        if auto_commit:
            self.db.commit()

    def get_rule_versions(self, rule_id: int) -> list[RuleVersion]:
        return (
            self.db.query(RuleVersion)
            .filter(RuleVersion.rule_id == rule_id)
            .order_by(RuleVersion.version.desc())
            .all()
        )

    def get_rule_version(self, rule_id: int, version: int) -> RuleVersion | None:
        return (
            self.db.query(RuleVersion)
            .filter(RuleVersion.rule_id == rule_id, RuleVersion.version == version)
            .first()
        )

    def get_version_diff(self, rule_id: int, version1: int, version2: int) -> dict[str, Any] | None:
        v1 = self.get_rule_version(rule_id, version1)
        v2 = self.get_rule_version(rule_id, version2)

        if not v1 or not v2:
            return None

        diff = {}
        fields = [
            "name",
            "description",
            "group",
            "priority",
            "enabled",
            "condition_dsl",
            "action",
            "rule_metadata",
        ]

        for field in fields:
            val1 = getattr(v1, field)
            val2 = getattr(v2, field)
            if val1 != val2:
                diff[field] = {"version1": val1, "version2": val2}

        return {
            "rule_id": rule_id,
            "version1": version1,
            "version2": version2,
            "differences": diff,
        }
