"""Duplicate validator - checks for duplicate rules."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from .base import ValidationResult, Validator

if TYPE_CHECKING:
    from sqlalchemy.orm import Session


class DuplicateValidator(Validator):
    """Validates for duplicate rules in database.

    Checks:
    - No duplicate rule names in same group
    - No duplicate condition DSL in same group
    """

    def __init__(self, db: Session):
        """Initialize with database session.

        Args:
            db: SQLAlchemy database session
        """
        self.db = db

    def validate(self, rule_data: dict[str, Any]) -> ValidationResult:
        """Validate for duplicates."""
        result = ValidationResult()

        # Skip if we don't have the necessary fields
        if not rule_data.get("name"):
            return result

        group = rule_data.get("group", "default")

        # Check for duplicate name in same group
        self._check_duplicate_name(rule_data, group, result)

        # Check for duplicate condition DSL in same group
        self._check_duplicate_condition(rule_data, group, result)

        return result

    def _check_duplicate_name(
        self, rule_data: dict[str, Any], group: str, result: ValidationResult
    ) -> None:
        """Check for duplicate rule names in the same group."""
        try:
            from fluxrules.api.models.rule import Rule

            name = rule_data.get("name")
            rule_id = rule_data.get("id")

            # Query for existing rules with same name in same group
            query = self.db.query(Rule).filter(
                Rule.name == name,
                Rule.group == group,
            )

            # If updating, exclude the current rule
            if rule_id:
                query = query.filter(Rule.id != rule_id)

            existing = query.first()

            if existing:
                result.add_warning(
                    "duplicate_name",
                    f"Rule with name '{name}' already exists in group '{group}' (ID: {existing.id})",
                    field="name",
                    details={"existing_rule_id": existing.id},
                )
        except Exception as e:
            result.add_info(
                "duplicate_check_skipped",
                f"Could not check for duplicate names: {e!s}",
            )

    def _check_duplicate_condition(
        self, rule_data: dict[str, Any], group: str, result: ValidationResult
    ) -> None:
        """Check for duplicate condition DSL in the same group."""
        try:
            from fluxrules.api.models.rule import Rule

            condition_dsl = rule_data.get("condition_dsl")
            if not condition_dsl:
                return

            # Normalize condition for comparison
            if isinstance(condition_dsl, dict):
                condition_str = json.dumps(condition_dsl, sort_keys=True)
            else:
                condition_str = condition_dsl

            rule_id = rule_data.get("id")

            # Query for existing rules with same condition in same group
            rules = self.db.query(Rule).filter(Rule.group == group).all()

            for rule in rules:
                # Skip if same rule (for updates)
                if rule_id and rule.id == rule_id:
                    continue

                # Compare conditions
                try:
                    if isinstance(rule.condition_dsl, dict):
                        existing_condition_str = json.dumps(rule.condition_dsl, sort_keys=True)
                    else:
                        existing_condition_str = rule.condition_dsl

                    if condition_str == existing_condition_str:
                        result.add_warning(
                            "duplicate_condition",
                            f"Rule with identical condition already exists in group '{group}' (ID: {rule.id}, Name: {rule.name})",
                            field="condition_dsl",
                            details={
                                "existing_rule_id": rule.id,
                                "existing_rule_name": rule.name,
                            },
                        )
                        break  # Only warn once
                except Exception:  # noqa: S112 - skip an unparseable existing rule
                    continue
        except Exception as e:
            result.add_info(
                "duplicate_condition_check_skipped",
                f"Could not check for duplicate conditions: {e!s}",
            )

    @property
    def validator_name(self) -> str:
        """Return validator name."""
        return "DuplicateValidator"
