"""Referential validator - checks for field existence and references."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from .base import ValidationResult, Validator

if TYPE_CHECKING:
    from sqlalchemy.orm import Session


class ReferentialValidator(Validator):
    """Validates referential integrity of fields mentioned in conditions.

    Checks:
    - Fields mentioned in conditions exist in the fact/context schema (if schema available)
    - Group exists (if group validation enabled)
    """

    def __init__(self, db: Session | None = None, schema: dict[str, Any] | None = None):
        """Initialize with optional database session and schema.

        Args:
            db: SQLAlchemy database session
            schema: Schema defining valid fields
        """
        self.db = db
        self.schema = schema or {}

    def validate(self, rule_data: dict[str, Any]) -> ValidationResult:
        """Validate referential integrity."""
        result = ValidationResult()

        # Check fields referenced in condition DSL
        self._check_condition_fields(rule_data, result)

        return result

    def _check_condition_fields(self, rule_data: dict[str, Any], result: ValidationResult) -> None:
        """Check if fields referenced in conditions exist in schema."""
        if not self.schema:
            # No schema, skip check
            return

        condition_dsl = rule_data.get("condition_dsl")
        if not isinstance(condition_dsl, dict):
            return

        # Collect all field references from condition
        fields: set[str] = set()
        self._collect_fields(condition_dsl, fields)

        # Check each field exists in schema
        valid_fields = set(self.schema.keys())
        for field in fields:
            if field not in valid_fields:
                result.add_warning(
                    "field_not_in_schema",
                    f"Field '{field}' referenced in condition is not in schema",
                    field="condition_dsl",
                    details={
                        "missing_field": field,
                        "valid_fields": list(valid_fields),
                    },
                )

    def _collect_fields(self, condition: dict[str, Any], fields: set[str]) -> None:
        """Recursively collect field names from condition DSL."""
        if condition.get("type") == "condition":
            field = condition.get("field")
            if field:
                fields.add(field)
        else:
            # Recursively process children
            for child in condition.get("children", []):
                if isinstance(child, dict):
                    self._collect_fields(child, fields)

    @property
    def validator_name(self) -> str:
        """Return validator name."""
        return "ReferentialValidator"
