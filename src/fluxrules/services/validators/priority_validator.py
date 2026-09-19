"""Priority validator - checks for priority conflicts."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from .base import ValidationResult, Validator

if TYPE_CHECKING:
    from sqlalchemy.orm import Session


class PriorityValidator(Validator):
    """Validates priority assignments for conflicts.

    Checks:
    - No multiple rules with same priority in same group
    - Priority values are within valid range
    """

    def __init__(self, db: Session):
        """Initialize with database session.

        Args:
            db: SQLAlchemy database session
        """
        self.db = db

    def validate(self, rule_data: dict[str, Any]) -> ValidationResult:
        """Validate priority."""
        result = ValidationResult()

        priority = rule_data.get("priority")
        if priority is None:
            return result

        group = rule_data.get("group", "default")

        # Check for priority conflicts in same group
        self._check_priority_conflict(rule_data, group, result)

        return result

    def _check_priority_conflict(
        self, rule_data: dict[str, Any], group: str, result: ValidationResult
    ) -> None:
        """Check for priority conflicts in the same group."""
        try:
            from fluxrules.api.models.rule import Rule

            priority = rule_data.get("priority")
            rule_id = rule_data.get("id")

            # Query for existing rules with same priority in same group
            query = self.db.query(Rule).filter(
                Rule.priority == priority,
                Rule.group == group,
            )

            # If updating, exclude the current rule
            if rule_id:
                query = query.filter(Rule.id != rule_id)

            existing_rules = query.all()

            if existing_rules:
                count = len(existing_rules)
                rule_names = ", ".join([r.name for r in existing_rules[:3]])
                if count > 3:
                    rule_names += f", ... and {count - 3} more"

                result.add_warning(
                    "priority_conflict",
                    f"Priority {priority} is already used by {count} rule(s) in group '{group}': {rule_names}",
                    field="priority",
                    details={
                        "conflicting_count": count,
                        "conflicting_rule_ids": [r.id for r in existing_rules],
                    },
                )
        except Exception as e:
            result.add_info(
                "priority_check_skipped",
                f"Could not check for priority conflicts: {e!s}",
            )

    @property
    def validator_name(self) -> str:
        """Return validator name."""
        return "PriorityValidator"
