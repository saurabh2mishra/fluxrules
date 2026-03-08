from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional
import json

from sqlalchemy.orm import Session

from app.models.rule import Rule
from app.schemas.rule import RuleCreate, RuleUpdate
from app.services.brms_service import BRMSService
from app.services.conflict_detector import ConflictDetector as LegacyConflictDetector

ValidationMode = Literal["legacy", "brms", "shadow"]


class RuleValidationService:
    """Bridge between legacy conflict checks and BRMS validations for A/B rollout."""

    CANDIDATE_RULE_ID = "__candidate_rule__"

    def __init__(self, db: Session):
        self.db = db
        self._legacy = LegacyConflictDetector(db)
        self._brms = BRMSService()

    def validate(self, rule_payload: Dict[str, Any], mode: ValidationMode, rule_id: Optional[int] = None) -> Dict[str, Any]:
        legacy_conflicts = self._legacy_conflicts(rule_payload, rule_id)
        brms_conflicts, brms_report = self._brms_conflicts(rule_payload, rule_id)

        primary_engine = "brms" if mode == "brms" else "legacy"
        selected_conflicts = brms_conflicts if primary_engine == "brms" else legacy_conflicts

        return {
            "valid": len(selected_conflicts) == 0,
            "conflicts": selected_conflicts,
            "validation_engine": {
                "mode": mode,
                "primary": primary_engine,
                "shadow_enabled": mode == "shadow",
            },
            "engines": {
                "legacy": {"conflicts": legacy_conflicts, "count": len(legacy_conflicts)},
                "brms": {"conflicts": brms_conflicts, "count": len(brms_conflicts)},
            },
            "brms_report": brms_report,
        }

    def _legacy_conflicts(self, rule_payload: Dict[str, Any], rule_id: Optional[int]) -> List[Dict[str, Any]]:
        if rule_id is None:
            return self._legacy.check_new_rule_conflicts(RuleCreate(**rule_payload))
        return self._legacy.check_update_rule_conflicts(rule_id, RuleUpdate(**rule_payload))

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
        dataset.append(candidate)

        report = self._brms.validate(dataset)
        conflicts: List[Dict[str, Any]] = []

        for item in report.get("conflicts", []):
            left = item.get("left_rule_id")
            right = item.get("right_rule_id")
            if self.CANDIDATE_RULE_ID not in (left, right):
                continue
            existing_id = right if left == self.CANDIDATE_RULE_ID else left
            conflicts.append(
                {
                    "type": "brms_overlap",
                    "existing_rule_id": int(existing_id) if str(existing_id).isdigit() else existing_id,
                    "existing_rule_name": self._name_for_rule_id(existing_rules, str(existing_id)),
                    "description": f"BRMS overlap detected with rule '{self._name_for_rule_id(existing_rules, str(existing_id))}' (ID: {existing_id}).",
                    "overlapping_fields": item.get("overlapping_fields", []),
                }
            )

        for item in report.get("dead_rules", []):
            if item.get("rule_id") != self.CANDIDATE_RULE_ID:
                continue
            conflicts.append(
                {
                    "type": "brms_dead_rule",
                    "existing_rule_id": None,
                    "existing_rule_name": None,
                    "description": "BRMS dead-rule detection found contradictory constraints in this rule.",
                    "field": item.get("field"),
                }
            )

        return conflicts, report

    @staticmethod
    def _name_for_rule_id(existing_rules: List[Rule], rule_id: str) -> str:
        for rule in existing_rules:
            if str(rule.id) == str(rule_id):
                return rule.name
        return str(rule_id)

