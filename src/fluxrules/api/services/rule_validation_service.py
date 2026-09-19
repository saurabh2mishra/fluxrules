from __future__ import annotations

import json
import logging
from typing import Any

from sqlalchemy.orm import Session

from fluxrules.api.models.rule import Rule
from fluxrules.api.services.brms_service import BRMSService
from fluxrules.services.validation_gateway import ValidationGateway

logger = logging.getLogger(__name__)


class RuleValidationService:
    """API validation service using library's ValidationGateway.

    Delegates structural, duplicate, priority, and BRMS validation to library
    validators through ValidationGateway, ensuring consistent validation
    across all code paths (API, Library, CLI).
    """

    def __init__(self, db: Session):
        self.db = db
        self.gateway = ValidationGateway(db)
        self._brms = BRMSService()

    def validate(self, rule_payload: dict[str, Any], rule_id: int | None = None) -> dict[str, Any]:
        """Validate rule using library's ValidationGateway + BRMS analysis + cross-group duplicate check.

        Returns API-compatible response format with conflicts and warnings.

        Note: StatefulDSLValidator is now part of ValidationGateway, not duplicated here.
        """
        # Use library validators in warning mode (don't raise exceptions)
        # Includes: Structural, StatefulDSL, Duplicate, Priority, BRMS, Action, Referential
        validation_result = self.gateway.validate(rule_payload, mode="warning")

        # Convert library validation issues to API conflict format
        conflicts = self._convert_validation_issues_to_conflicts(validation_result, rule_id)

        # For API, upgrade certain warnings to blocking conflicts
        # These must be treated as errors in the API context
        blocking_warning_types = {
            "priority_conflict",
            "duplicate_condition",
            "duplicate_name",
        }
        for warning in validation_result.get_warnings():
            if warning.type in blocking_warning_types:
                # Convert to conflict
                api_type = (
                    "priority_collision" if warning.type == "priority_conflict" else warning.type
                )
                conflict = {
                    "type": api_type,
                    "description": warning.message,
                    "severity": "error",
                }

                # Extract existing_rule_id from details if present
                if warning.details:
                    if warning.details.get("conflicting_rule_ids"):
                        conflict["existing_rule_id"] = warning.details["conflicting_rule_ids"][0]
                    elif warning.details.get("existing_rule_id"):
                        conflict["existing_rule_id"] = warning.details["existing_rule_id"]
                    conflict.update(warning.details)

                # Only add if not self-reference
                if rule_id is None or conflict.get("existing_rule_id") != rule_id:
                    conflicts.append(conflict)
                    logger.debug(f"Upgraded warning to conflict: {conflict}")

        # Add cross-group duplicate condition + action check (API-specific requirement)
        cross_group_dupes = self._check_cross_group_duplicates(rule_payload, rule_id)
        conflicts.extend(cross_group_dupes)

        # Get BRMS-specific report (for detailed analysis + additional conflicts)
        brms_report = self._get_brms_report(rule_payload, rule_id)

        # Extract additional conflicts from BRMS report
        brms_conflicts = self._extract_brms_conflicts(brms_report, rule_id)
        conflicts.extend(brms_conflicts)

        return {
            "valid": len(conflicts) == 0,
            "conflicts": conflicts,
            "warnings": self._extract_warnings(validation_result),
            "brms_report": brms_report,
        }

    def _convert_validation_issues_to_conflicts(
        self, validation_result: Any, rule_id: int | None = None
    ) -> list[dict[str, Any]]:
        """Convert library ValidationResult errors to API conflict format.

        Note: Only converts ERRORS to conflicts. Warnings stay as warnings.
        """
        conflicts = []

        # Map library issue types to API conflict types
        type_mapping = {
            "priority_conflict": "priority_collision",  # API expects priority_collision
        }

        # Only process errors, not warnings (warnings are kept separate)
        for issue in validation_result.get_errors():
            conflict_type = issue.type
            api_type = type_mapping.get(conflict_type, conflict_type)

            conflict = {
                "type": api_type,
                "description": issue.message,
                "severity": issue.severity.value,
            }

            # Map issue fields to conflict fields for API compatibility
            if issue.rule_id:
                conflict["existing_rule_id"] = issue.rule_id

            # Include details
            if issue.details:
                # For priority/duplicate conflicts, extract existing_rule_id first
                if not conflict.get("existing_rule_id"):
                    if issue.details.get("conflicting_rule_ids"):
                        conflict["existing_rule_id"] = issue.details["conflicting_rule_ids"][0]
                    elif issue.details.get("existing_rule_id"):
                        conflict["existing_rule_id"] = issue.details["existing_rule_id"]

                # Then merge details
                conflict.update(issue.details)

            # Exclude self-references when updating
            if rule_id is not None and conflict.get("existing_rule_id") == rule_id:
                continue

            logger.debug(f"Converted conflict: {conflict}")
            conflicts.append(conflict)

        return conflicts

    def _extract_warnings(self, validation_result: Any) -> list[dict[str, Any]]:
        """Extract warnings from validation result."""
        warnings = []
        for issue in validation_result.get_warnings():
            warnings.append(
                {
                    "type": issue.type,
                    "description": issue.message,
                }
            )
        return warnings

    def _extract_brms_conflicts(
        self, brms_report: dict[str, Any], rule_id: int | None = None
    ) -> list[dict[str, Any]]:
        """Extract blocking conflicts from BRMS report."""
        conflicts = []

        # Dead rules are blocking
        for dead_rule in brms_report.get("dead_rules", []):
            if dead_rule.get("rule_id") == "__candidate__":
                conflicts.append(
                    {
                        "type": "brms_dead_rule",
                        "description": dead_rule.get("reason", "Dead rule detected"),
                        "severity": "error",
                        "field": dead_rule.get("field"),
                    }
                )

        # BRMS overlaps are blocking
        for conflict in brms_report.get("conflicts", []):
            left_id = conflict.get("left_rule_id")
            right_id = conflict.get("right_rule_id")

            if "__candidate__" in (left_id, right_id):
                existing_id = right_id if left_id == "__candidate__" else left_id
                conflicts.append(
                    {
                        "type": "brms_overlap",
                        "existing_rule_id": int(existing_id)
                        if str(existing_id).isdigit()
                        else existing_id,
                        "description": f"BRMS overlap detected: {conflict.get('description', 'Rules have overlapping conditions')}",
                        "severity": "error",
                        "overlapping_fields": conflict.get("overlapping_fields", []),
                    }
                )

        return conflicts

    def _get_brms_report(self, rule_payload: dict[str, Any], rule_id: int | None) -> dict[str, Any]:
        """Get detailed BRMS analysis report."""
        try:
            candidate_group = rule_payload.get("group") or "default"

            base_query = self.db.query(Rule).filter(Rule.enabled.is_(True))
            if rule_id is not None:
                base_query = base_query.filter(Rule.id != rule_id)

            same_group_rules = base_query.filter(Rule.group == candidate_group).all()

            dataset: list[dict[str, Any]] = []
            for rule in same_group_rules:
                dataset.append(self._rule_to_payload(rule))

            candidate = {
                "id": "__candidate__",
                "name": rule_payload.get("name"),
                "group": candidate_group,
                "priority": rule_payload.get("priority", 0),
                "enabled": rule_payload.get("enabled", True),
                "condition_dsl": rule_payload.get("condition_dsl") or {},
                "action": rule_payload.get("action") or "",
            }

            report = self._brms.validate_candidate(
                candidate_payload=candidate,
                existing_payloads=dataset,
                group=candidate_group,
            )

            return report
        except Exception as e:
            logger.warning(f"BRMS report generation failed: {e}")
            return {}

    @staticmethod
    def _rule_to_payload(rule: Rule) -> dict[str, Any]:
        """Convert Rule ORM to payload dict."""
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

    def _validate_stateful_dsl(self, condition_dsl: dict[str, Any]) -> list[dict[str, Any]]:
        """Validate stateful DSL nodes (sequence, cross_fact_join, count_threshold).

        These are API-specific validations not handled by library validators.
        """
        errors: list[dict[str, Any]] = []
        warnings: list[dict[str, Any]] = []

        if not isinstance(condition_dsl, dict) or not condition_dsl:
            return errors

        self._validate_top_level_stateful_exclusivity(condition_dsl, errors)
        self._walk_stateful_nodes(condition_dsl, errors, warnings, path="$")

        # Convert errors to conflict format
        conflicts = [
            {
                "type": e.get("type", "dsl_validation_error"),
                "description": e.get("description", ""),
                "path": e.get("path", ""),
            }
            for e in errors
        ]

        return conflicts

    def _validate_top_level_stateful_exclusivity(
        self, condition_dsl: dict[str, Any], errors: list[dict[str, Any]]
    ) -> None:
        """Validate that top-level stateful nodes don't mix families."""
        stateful_families = {"sequence", "cross_fact_join", "count_threshold"}
        top_level_families: set = set()

        root_type = condition_dsl.get("type")
        if root_type == "group":
            for child in condition_dsl.get("children", []) or []:
                if isinstance(child, dict) and child.get("type") in stateful_families:
                    top_level_families.add(child["type"])
        elif root_type in stateful_families:
            top_level_families.add(root_type)

        if len(top_level_families) > 1:
            families = ", ".join(sorted(top_level_families))
            errors.append(
                {
                    "type": "dsl_validation_error",
                    "description": f"Top-level stateful node families are mutually exclusive; found: {families}.",
                    "path": "$",
                }
            )

    def _walk_stateful_nodes(
        self,
        node: Any,
        errors: list[dict[str, Any]],
        warnings: list[dict[str, Any]],
        path: str,
    ) -> None:
        """Recursively validate stateful DSL nodes."""
        if isinstance(node, list):
            for idx, child in enumerate(node):
                self._walk_stateful_nodes(child, errors, warnings, f"{path}[{idx}]")
            return
        if not isinstance(node, dict):
            return

        node_type = node.get("type")

        if node_type == "sequence":
            steps = node.get("steps")
            if steps is None:
                errors.append(
                    {
                        "type": "dsl_validation_error",
                        "description": "sequence requires 'steps' field.",
                        "path": f"{path}.steps",
                    }
                )
            elif not isinstance(steps, list):
                errors.append(
                    {
                        "type": "dsl_validation_error",
                        "description": "sequence.steps must be an array.",
                        "path": f"{path}.steps",
                    }
                )
            else:
                if len(steps) < 2:
                    errors.append(
                        {
                            "type": "dsl_validation_error",
                            "description": "sequence.steps >= 2 (minimum 2 steps required).",
                            "path": f"{path}.steps",
                        }
                    )
                # Warn if all steps are identical
                if len(steps) >= 2:
                    normalized_steps = [
                        json.dumps(step, sort_keys=True) for step in steps if isinstance(step, dict)
                    ]
                    if len(set(normalized_steps)) == 1:
                        warnings.append(
                            {
                                "type": "dsl_validation_warning",
                                "description": "sequence pattern is equivalent to count-threshold intent; consider using count_threshold.",
                                "path": path,
                            }
                        )

        if node_type == "cross_fact_join":
            facts = node.get("facts")
            if facts is None:
                errors.append(
                    {
                        "type": "dsl_validation_error",
                        "description": "cross_fact_join requires 'facts' field.",
                        "path": f"{path}.facts",
                    }
                )
            elif not isinstance(facts, list):
                errors.append(
                    {
                        "type": "dsl_validation_error",
                        "description": "cross_fact_join.facts must be an array.",
                        "path": f"{path}.facts",
                    }
                )
            elif len(facts) < 2:
                errors.append(
                    {
                        "type": "dsl_validation_error",
                        "description": "cross_fact_join.facts >= 2 (minimum 2 facts required).",
                        "path": f"{path}.facts",
                    }
                )

        for key, value in node.items():
            if isinstance(value, (dict, list)):
                child_path = f"{path}.{key}" if path != "$" else f"$.{key}"
                self._walk_stateful_nodes(value, errors, warnings, child_path)

    def _check_cross_group_duplicates(
        self, rule_payload: dict[str, Any], rule_id: int | None = None
    ) -> list[dict[str, Any]]:
        """Check for duplicate condition+action across all groups (API-specific).

        In the API, having identical condition AND action in different groups is redundant.
        """
        conflicts: list[dict[str, Any]] = []

        condition_dsl = rule_payload.get("condition_dsl")
        action = rule_payload.get("action")

        if not condition_dsl or not action:
            logger.debug(
                f"Skipping cross-group duplicate check: condition_dsl={bool(condition_dsl)}, action={bool(action)}"
            )
            return conflicts

        try:
            # Normalize condition for comparison
            if isinstance(condition_dsl, dict):
                condition_str = json.dumps(condition_dsl, sort_keys=True)
            else:
                condition_str = condition_dsl

            logger.debug(f"Checking cross-group duplicates for condition: {condition_str[:100]}...")

            # Query all enabled rules (excluding current rule if updating)
            query = self.db.query(Rule).filter(Rule.enabled.is_(True))
            if rule_id is not None:
                query = query.filter(Rule.id != rule_id)

            existing_rules = query.all()
            logger.debug(f"Found {len(existing_rules)} existing enabled rules to check against")

            for rule in existing_rules:
                try:
                    # Parse condition_dsl whether it's stored as dict or string
                    if isinstance(rule.condition_dsl, dict):
                        rule_condition_obj = rule.condition_dsl
                    elif isinstance(rule.condition_dsl, str):
                        try:
                            rule_condition_obj = json.loads(rule.condition_dsl)
                        except (json.JSONDecodeError, TypeError):
                            rule_condition_obj = None
                    else:
                        rule_condition_obj = None

                    if rule_condition_obj is None:
                        continue

                    # Serialize with sort_keys for consistent comparison
                    existing_condition_str = json.dumps(rule_condition_obj, sort_keys=True)

                    # Check if same condition AND action (across any group)
                    conditions_match = condition_str == existing_condition_str
                    actions_match = action == rule.action
                    logger.debug(
                        f"Rule '{rule.name}': conditions_match={conditions_match}, actions_match={actions_match}"
                    )

                    if conditions_match and actions_match:
                        logger.debug(f"Found duplicate! Rule '{rule.name}' (ID: {rule.id})")
                        conflicts.append(
                            {
                                "type": "duplicate_condition",
                                "description": f"Rule with identical condition and action already exists: '{rule.name}' (ID: {rule.id}) in group '{rule.group}'",
                                "severity": "error",
                                "existing_rule_id": rule.id,
                                "existing_rule_name": rule.name,
                            }
                        )
                        break  # Only report first match
                except Exception as e:
                    logger.debug(f"Error checking rule {rule.id}: {e}")
                    continue
        except Exception as e:
            logger.debug(f"Cross-group duplicate check failed: {e}")

        logger.debug(f"Cross-group duplicate check returned {len(conflicts)} conflicts")
        return conflicts
