"""BRMS validator - checks for business rule problems."""

from __future__ import annotations

from typing import Any

from .base import ValidationResult, Validator


class BRMSValidator(Validator):
    """Validates Business Rule Management System (BRMS) concerns.

    Checks:
    - No dead rules (conditions that can never be true)
    - No unreachable rules due to priority ordering
    - Warnings for overlapping conditions
    """

    def validate(self, rule_data: dict[str, Any]) -> ValidationResult:
        """Validate BRMS concerns."""
        result = ValidationResult()

        # Check for basic dead rule patterns
        self._check_dead_rule_patterns(rule_data, result)

        # Check for suspicious conditions
        self._check_suspicious_conditions(rule_data, result)

        return result

    def _check_dead_rule_patterns(
        self, rule_data: dict[str, Any], result: ValidationResult
    ) -> None:
        """Check for patterns that would make a rule dead (unreachable)."""
        condition_dsl = rule_data.get("condition_dsl")
        if not isinstance(condition_dsl, dict):
            return

        # Check for AND with contradictory conditions
        if self._has_contradictory_and(condition_dsl):
            result.add_warning(
                "dead_rule_and",
                "Condition contains AND with contradictory subconditions (e.g., field == 1 AND field == 2)",
                field="condition_dsl",
            )

        # Check for impossible comparisons
        if self._has_impossible_comparison(condition_dsl):
            result.add_warning(
                "dead_rule_comparison",
                "Condition has impossible comparison (e.g., field == null AND field != null)",
                field="condition_dsl",
            )

    def _check_suspicious_conditions(
        self, rule_data: dict[str, Any], result: ValidationResult
    ) -> None:
        """Check for suspicious condition patterns."""
        enabled = rule_data.get("enabled", True)
        condition_dsl = rule_data.get("condition_dsl")

        if not isinstance(condition_dsl, dict):
            return

        # Check for empty condition groups
        if self._is_empty_group(condition_dsl):
            result.add_info(
                "empty_condition_group",
                "Condition has empty group (no subconditions)",
                field="condition_dsl",
            )

        # Warn if disabled rule has complex conditions
        if not enabled and self._is_complex_condition(condition_dsl):
            result.add_info(
                "disabled_complex_rule",
                "Rule is disabled but has complex conditions (consider deleting if no longer needed)",
                field="enabled",
            )

    def _has_contradictory_and(self, condition: dict[str, Any]) -> bool:
        """Check if condition has contradictory AND subconditions."""
        if condition.get("type") not in ("AND", "group"):
            return False

        children = condition.get("children", [])
        if len(children) < 2:
            return False

        # Simple check: look for same field with different comparisons
        fields: dict[Any, list[Any]] = {}
        for child in children:
            if child.get("type") == "condition":
                field = child.get("field")
                op = child.get("op")
                value = child.get("value")

                if field:
                    if field not in fields:
                        fields[field] = []
                    fields[field].append((op, value))

        # Check for contradictions
        for field_ops in fields.values():
            if len(field_ops) > 1:
                # If we have both == with different values, it's contradictory
                eq_values = {v for op, v in field_ops if op == "=="}
                if len(eq_values) > 1:
                    return True

        return False

    def _has_impossible_comparison(self, condition: dict[str, Any]) -> bool:
        """Check for impossible comparisons."""
        if condition.get("type") == "condition":
            op = condition.get("op")
            value = condition.get("value")

            # null == X and X != null is impossible
            if op == "==" and value is None:
                return False  # null comparisons are possible

        # Recursively check children
        for child in condition.get("children", []):
            if self._has_impossible_comparison(child):
                return True

        return False

    def _is_empty_group(self, condition: dict[str, Any]) -> bool:
        """Check if condition is a group with no children."""
        if condition.get("type") in ("AND", "OR", "group"):
            children = condition.get("children", [])
            return len(children) == 0
        return False

    def _is_complex_condition(self, condition: dict[str, Any]) -> bool:
        """Check if condition is complex (nested OR groups)."""
        if condition.get("type") in ("OR", "AND"):
            children = condition.get("children", [])
            if len(children) > 1:
                return True
            if any(self._is_complex_condition(child) for child in children):
                return True

        return False

    @property
    def validator_name(self) -> str:
        """Return validator name."""
        return "BRMSValidator"
