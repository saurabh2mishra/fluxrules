from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from app.models.rule import Rule
from app.schemas.rule import RuleCreate, RuleUpdate
from app.services.brms_service import BRMSService
from app.validation._compiled_cache import invalidate as invalidate_compiled_cache

logger = logging.getLogger(__name__)


class RuleValidationService:
    """
    BRMS-powered rule validation service.

    Uses **incremental, group-scoped** validation:
      - Only loads existing rules in the same group as the candidate.
      - Uses ``BRMSService.validate_candidate`` (index-based, O(k log n)).
      - Falls back to full validation when no group is provided.
    """

    CANDIDATE_RULE_ID = "__candidate_rule__"

    def __init__(self, db: Session):
        self.db = db
        self._brms = BRMSService()

    def validate(self, rule_payload: Dict[str, Any], rule_id: Optional[int] = None) -> Dict[str, Any]:
        brms_conflicts, brms_report = self._brms_conflicts(rule_payload, rule_id)

        return {
            "valid": len(brms_conflicts) == 0,
            "conflicts": brms_conflicts,
            "brms_report": brms_report,
        }

    # ------------------------------------------------------------------
    # Core — incremental, group-scoped BRMS validation
    # ------------------------------------------------------------------

    def _brms_conflicts(
        self, rule_payload: Dict[str, Any], rule_id: Optional[int]
    ) -> tuple[List[Dict[str, Any]], Dict[str, Any]]:
        candidate_group = rule_payload.get("group") or "default"

        # ── Load only same-group rules (group-scoped) ──
        base_query = self.db.query(Rule).filter(Rule.enabled.is_(True))

        # Exclude the rule being edited from all queries up-front
        if rule_id is not None:
            base_query = base_query.filter(Rule.id != rule_id)

        # For duplicate-condition check we also need cross-group rules with
        # the same condition+action.  We load same-group for conflict detection,
        # and separately check duplicates cross-group below.
        same_group_rules = base_query.filter(Rule.group == candidate_group).all()
        # Also grab all rules for duplicate checking (lightweight — only condition/action)
        all_enabled_rules = base_query.all()

        dataset: List[Dict[str, Any]] = []
        for rule in same_group_rules:
            dataset.append(self._rule_to_payload(rule))

        candidate = {
            "id": self.CANDIDATE_RULE_ID,
            "name": rule_payload.get("name"),
            "group": candidate_group,
            "priority": rule_payload.get("priority", 0),
            "enabled": rule_payload.get("enabled", True),
            "condition_dsl": rule_payload.get("condition_dsl") or {},
            "action": rule_payload.get("action") or "",
        }

        # ── Incremental candidate-only validation ──
        report = self._brms.validate_candidate(
            candidate_payload=candidate,
            existing_payloads=dataset,
            group=candidate_group,
        )

        conflicts: List[Dict[str, Any]] = []

        # ── Duplicate condition+action detection (cross-group) ──
        candidate_condition = json.dumps(candidate["condition_dsl"], sort_keys=True)
        candidate_action = (candidate.get("action") or "").strip()
        for rule in all_enabled_rules:
            existing_condition = (
                json.loads(rule.condition_dsl)
                if isinstance(rule.condition_dsl, str)
                else rule.condition_dsl
            )
            existing_action = (rule.action or "").strip()
            if (
                json.dumps(existing_condition, sort_keys=True) == candidate_condition
                and existing_action == candidate_action
            ):
                conflicts.append(
                    {
                        "type": "duplicate_condition",
                        "existing_rule_id": rule.id,
                        "existing_rule_name": rule.name,
                        "description": (
                            f"Duplicate rule detected: rule '{rule.name}' (ID: {rule.id}) "
                            f"has identical condition and action."
                        ),
                    }
                )

        # ── BRMS duplicates (from incremental validator) ──
        for dup in report.get("duplicates", []):
            dup_rule1 = str(dup.get("rule1_id", "")) if isinstance(dup, dict) else str(getattr(dup, "rule1_id", ""))
            dup_rule2 = str(dup.get("rule2_id", "")) if isinstance(dup, dict) else str(getattr(dup, "rule2_id", ""))
            if self.CANDIDATE_RULE_ID not in (dup_rule1, dup_rule2):
                continue
            existing_id = dup_rule2 if dup_rule1 == self.CANDIDATE_RULE_ID else dup_rule1
            if existing_id == self.CANDIDATE_RULE_ID:
                continue
            matching_rule = next(
                (r for r in all_enabled_rules if str(r.id) == str(existing_id)), None
            )
            if matching_rule and (matching_rule.action or "").strip() != candidate_action:
                continue
            already_found = any(
                c.get("type") == "duplicate_condition"
                and str(c.get("existing_rule_id")) == str(existing_id)
                for c in conflicts
            )
            if not already_found:
                conflicts.append(
                    {
                        "type": "duplicate_condition",
                        "existing_rule_id": (
                            int(existing_id) if str(existing_id).isdigit() else existing_id
                        ),
                        "existing_rule_name": self._name_for_rule_id(
                            all_enabled_rules, str(existing_id)
                        ),
                        "description": (
                            f"Duplicate condition detected with rule "
                            f"'{self._name_for_rule_id(all_enabled_rules, str(existing_id))}' "
                            f"(ID: {existing_id})."
                        ),
                    }
                )

        # ── Priority collision detection (same group only) ──
        candidate_priority = candidate["priority"]
        for rule in same_group_rules:
            if rule.priority == candidate_priority and rule.group == candidate_group:
                conflicts.append(
                    {
                        "type": "priority_collision",
                        "existing_rule_id": rule.id,
                        "existing_rule_name": rule.name,
                        "description": (
                            f"Priority collision detected with rule '{rule.name}' "
                            f"(ID: {rule.id}) in group '{rule.group}'."
                        ),
                        "group": rule.group,
                        "priority": rule.priority,
                    }
                )

        # ── BRMS overlap conflicts ──
        for item in report.get("conflicts", []):
            left = item.get("left_rule_id") if isinstance(item, dict) else getattr(item, "left_rule_id", None)
            right = item.get("right_rule_id") if isinstance(item, dict) else getattr(item, "right_rule_id", None)
            if self.CANDIDATE_RULE_ID not in (left, right):
                continue
            existing_id = right if left == self.CANDIDATE_RULE_ID else left
            if existing_id == self.CANDIDATE_RULE_ID:
                continue
            overlapping_fields = (
                item.get("overlapping_fields")
                if isinstance(item, dict)
                else getattr(item, "overlapping_fields", [])
            )
            conflicts.append(
                {
                    "type": "brms_overlap",
                    "existing_rule_id": (
                        int(existing_id) if str(existing_id).isdigit() else existing_id
                    ),
                    "existing_rule_name": self._name_for_rule_id(
                        all_enabled_rules, str(existing_id)
                    ),
                    "description": (
                        f"BRMS overlap detected with rule "
                        f"'{self._name_for_rule_id(all_enabled_rules, str(existing_id))}' "
                        f"(ID: {existing_id})."
                    ),
                    "overlapping_fields": overlapping_fields,
                }
            )

        # ── Dead rules ──
        candidate_dead_rule = None
        for item in report.get("dead_rules", []):
            rid = item.get("rule_id") if isinstance(item, dict) else getattr(item, "rule_id", None)
            if rid == self.CANDIDATE_RULE_ID:
                candidate_dead_rule = item
                break
        if candidate_dead_rule:
            reason = (
                candidate_dead_rule.get("reason")
                if isinstance(candidate_dead_rule, dict)
                else getattr(candidate_dead_rule, "reason", None)
            )
            field = (
                candidate_dead_rule.get("field")
                if isinstance(candidate_dead_rule, dict)
                else getattr(candidate_dead_rule, "field", None)
            )
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

        # ── Safety net: never report self-conflicts ──
        if rule_id is not None:
            conflicts = [
                c for c in conflicts
                if str(c.get("existing_rule_id")) != str(rule_id)
            ]

        return conflicts, report

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _rule_to_payload(rule: Rule) -> Dict[str, Any]:
        return {
            "id": str(rule.id),
            "name": rule.name,
            "group": rule.group,
            "priority": rule.priority,
            "enabled": rule.enabled,
            "condition_dsl": (
                json.loads(rule.condition_dsl)
                if isinstance(rule.condition_dsl, str)
                else rule.condition_dsl
            ),
            "action": rule.action,
        }

    @staticmethod
    def _name_for_rule_id(existing_rules: List[Rule], rule_id: str) -> str:
        for rule in existing_rules:
            if str(rule.id) == str(rule_id):
                return rule.name
        return str(rule_id)

