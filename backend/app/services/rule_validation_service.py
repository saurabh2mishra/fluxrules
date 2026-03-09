from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional
import json

from sqlalchemy.orm import Session

from app.models.rule import Rule
from app.schemas.rule import RuleCreate, RuleUpdate
from app.services.brms_service import BRMSService

ValidationMode = Literal["legacy", "brms", "shadow"]


class RuleValidationService:
    """Bridge between legacy conflict checks and BRMS validations for A/B rollout."""

    CANDIDATE_RULE_ID = "__candidate_rule__"

    def __init__(self, db: Session):
        self.db = db
        self._brms = BRMSService()

    def validate(self, rule_payload: Dict[str, Any], mode: ValidationMode, rule_id: Optional[int] = None) -> Dict[str, Any]:
        brms_conflicts, brms_report = self._brms_conflicts(rule_payload, rule_id)

        primary_engine = "legacy" if mode == "shadow" else "brms"
        engines = {"brms": {"conflicts": brms_conflicts, "count": len(brms_conflicts)}}
        if mode == "shadow":
            engines["legacy"] = {"conflicts": [], "count": 0}

        return {
            "valid": len(brms_conflicts) == 0,
            "conflicts": brms_conflicts,
            "validation_engine": {
                "mode": mode,
                "primary": primary_engine,
                "shadow_enabled": mode == "shadow",
            },
            "engines": engines,
            "brms_report": brms_report,
        }

    def _brms_conflicts(self, rule_payload: Dict[str, Any], rule_id: Optional[int]) -> tuple[List[Dict[str, Any]], Dict[str, Any]]:
        existing_rules = self.db.query(Rule).filter(Rule.enabled.is_(True)).all()
        dataset = []
        for rule in existing_rules:
            if rule_id is not None and rule.id == rule_id:
                continue
            dataset.append(
                {
                    "id": str(rule.id),
                    "name": rule.name,
                    "group": rule.group,
                    "priority": rule.priority,
                    "enabled": rule.enabled,
                    "condition_dsl": json.loads(rule.condition_dsl) if isinstance(rule.condition_dsl, str) else rule.condition_dsl,
                    "action": rule.action,
                }
            )

        candidate = {
            "id": self.CANDIDATE_RULE_ID,
            "name": rule_payload.get("name"),
            "group": rule_payload.get("group"),
            "priority": rule_payload.get("priority", 0),
            "enabled": rule_payload.get("enabled", True),
            "condition_dsl": rule_payload.get("condition_dsl") or {},
            "action": rule_payload.get("action") or "",
        }
        # Ensure candidate rule ID is always __candidate_rule__
        candidate["id"] = self.CANDIDATE_RULE_ID
        dataset.append(candidate)

        report = self._brms.validate(dataset)
        conflicts: List[Dict[str, Any]] = []

        # Priority collision detection
        candidate_priority = candidate["priority"]
        candidate_group = candidate["group"]
        for rule in existing_rules:
            # For edit, skip the rule being edited
            if rule_id is not None and rule.id == rule_id:
                continue
            if rule.priority == candidate_priority and rule.group == candidate_group:
                conflicts.append(
                    {
                        "type": "priority_collision",
                        "existing_rule_id": rule.id,
                        "existing_rule_name": rule.name,
                        "description": f"Priority collision detected with rule '{rule.name}' (ID: {rule.id}) in group '{rule.group}'.",
                        "group": rule.group,
                        "priority": rule.priority,
                    }
                )

        # BRMS conflict detection
        for item in report.get("conflicts", []):
            left = getattr(item, "left_rule_id", None)
            right = getattr(item, "right_rule_id", None)
            # Ignore self-conflict (candidate vs itself)
            if self.CANDIDATE_RULE_ID not in (left, right):
                continue
            existing_id = right if left == self.CANDIDATE_RULE_ID else left
            if existing_id == self.CANDIDATE_RULE_ID:
                continue  # skip self-conflict
            conflicts.append(
                {
                    "type": "brms_overlap",
                    "existing_rule_id": int(existing_id) if str(existing_id).isdigit() else existing_id,
                    "existing_rule_name": self._name_for_rule_id(existing_rules, str(existing_id)),
                    "description": f"BRMS overlap detected with rule '{self._name_for_rule_id(existing_rules, str(existing_id))}' (ID: {existing_id}).",
                    "overlapping_fields": getattr(item, "overlapping_fields", []),
                }
            )

        # Ensure dead rules are surfaced in conflicts
        candidate_dead_rule = None
        for item in report.get("dead_rules", []):
            rule_id = item.get("rule_id") if isinstance(item, dict) else getattr(item, "rule_id", None)
            if rule_id == self.CANDIDATE_RULE_ID:
                candidate_dead_rule = item
                break
        if candidate_dead_rule:
            reason = candidate_dead_rule.get("reason") if isinstance(candidate_dead_rule, dict) else getattr(candidate_dead_rule, "reason", None)
            field = candidate_dead_rule.get("field") if isinstance(candidate_dead_rule, dict) else getattr(candidate_dead_rule, "field", None)
            conflicts.append(
                {
                    "type": "brms_dead_rule",
                    "existing_rule_id": None,
                    "existing_rule_name": None,
                    "description": f"BRMS dead-rule detection: {reason or 'contradictory constraints'}",
                    "field": field,
                    "reason": reason,
                }
            )
        return conflicts, report

    @staticmethod
    def _name_for_rule_id(existing_rules: List[Rule], rule_id: str) -> str:
        for rule in existing_rules:
            if str(rule.id) == str(rule_id):
                return rule.name
        return str(rule_id)

