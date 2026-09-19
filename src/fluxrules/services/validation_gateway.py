"""Unified validation gateway - central entry point for all rule validation."""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING, Any

from fluxrules.services.validators import (
    ActionValidator,
    BRMSValidator,
    CompositeValidator,
    DuplicateValidator,
    PriorityValidator,
    ReferentialValidator,
    StatefulDSLValidator,
    StructuralValidator,
    ValidationResult,
)

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


class ValidationException(Exception):
    """Exception raised when validation fails in strict mode."""

    def __init__(self, message: str, validation_result: ValidationResult):
        """Initialize with message and validation result.

        Args:
            message: Error message
            validation_result: ValidationResult object with details
        """
        self.message = message
        self.validation_result = validation_result
        super().__init__(message)


class ValidationGateway:
    """Unified validation gateway for all rule creation paths.

    This is the single entry point for all rule validation across:
    - API endpoints
    - Service layer
    - UnifiedRule persistence
    - RuleBuilder
    - YAML/CSV loaders
    - CLI
    - Engine

    Ensures consistent validation regardless of how rules are created.
    """

    def __init__(self, db: Session):
        """Initialize with database session.

        Args:
            db: SQLAlchemy database session
        """
        self.db = db
        self._validators = self._build_validators()

    def _build_validators(self) -> CompositeValidator:
        """Build the composite validator with all sub-validators.

        Returns:
            CompositeValidator with all validators in proper order
        """
        validators = [
            StructuralValidator(),  # First: structural validity
            StatefulDSLValidator(),  # Then: stateful DSL validity
            DuplicateValidator(self.db),  # Then: database checks
            PriorityValidator(self.db),  # Then: priority checks
            BRMSValidator(),  # Then: business rule checks
            ActionValidator(),  # Then: action validity
            ReferentialValidator(self.db),  # Finally: referential checks
        ]

        return CompositeValidator(validators, name="UnifiedRuleValidator")

    def validate(
        self,
        rule_data: dict[str, Any] | Any,
        mode: str = "strict",
    ) -> ValidationResult:
        """Validate rule data and return validation result.

        Args:
            rule_data: Rule data to validate (dict or Rule object)
            mode: Validation mode
                - "strict": Raise exception on errors (default)
                - "warning": Log warnings, return result
                - "skip": No validation

        Returns:
            ValidationResult with any issues found

        Raises:
            ValidationException: If mode=="strict" and errors found
        """
        if mode == "skip":
            return ValidationResult()

        # Convert rule_data to dict if needed
        rule_dict = self._normalize_rule_data(rule_data)

        # Run validation
        result = self._validators.validate(rule_dict)

        # Enforce based on mode
        if mode == "strict" and result.has_errors():
            error_messages = [f"  - {issue.message}" for issue in result.get_errors()]
            message = "Rule validation failed:\n" + "\n".join(error_messages)
            logger.error(message)
            raise ValidationException(message, result)

        # Log warnings
        if result.has_warnings():
            warnings = [f"  - {issue.message}" for issue in result.get_warnings()]
            warning_message = "Rule validation warnings:\n" + "\n".join(warnings)
            logger.warning(warning_message)

        return result

    def validate_and_log(
        self,
        rule_data: dict[str, Any] | Any,
        user_id: int | None = None,
        mode: str = "strict",
    ) -> tuple[dict[str, Any], ValidationResult]:
        """Validate rule and log the result.

        Args:
            rule_data: Rule data to validate
            user_id: User creating the rule (for logging)
            mode: Validation mode ("strict", "warning", "skip")

        Returns:
            (rule_dict, validation_result)

        Raises:
            ValidationException: If mode=="strict" and errors found
        """
        rule_dict = self._normalize_rule_data(rule_data)
        result = self.validate(rule_dict, mode=mode)

        # Log validation
        logger.info(
            f"Rule validation: {rule_dict.get('name', 'unknown')} "
            f"(user={user_id}, errors={len(result.get_errors())}, "
            f"warnings={len(result.get_warnings())})"
        )

        return rule_dict, result

    def _normalize_rule_data(self, rule_data: dict[str, Any] | Any) -> dict[str, Any]:
        """Convert rule_data to dict format.

        Args:
            rule_data: Rule data (dict, RuleCreate, Rule, etc)

        Returns:
            Normalized dict representation
        """
        if isinstance(rule_data, dict):
            return rule_data

        # Try to convert Pydantic model
        if hasattr(rule_data, "model_dump"):
            data = rule_data.model_dump(exclude_none=False)
            # Convert JSON strings to dicts
            if isinstance(data.get("condition_dsl"), str):
                try:
                    data["condition_dsl"] = json.loads(data["condition_dsl"])
                except (json.JSONDecodeError, TypeError):
                    pass
            return data

        # Try to convert SQLAlchemy model
        if hasattr(rule_data, "__table__"):
            data = {}
            for column in rule_data.__table__.columns:
                value = getattr(rule_data, column.name, None)
                if column.name == "condition_dsl" and isinstance(value, str):
                    try:
                        value = json.loads(value)
                    except (json.JSONDecodeError, TypeError):
                        pass
                data[column.name] = value
            return data

        # Fall back to dict() if available
        if hasattr(rule_data, "__dict__"):
            return {k: v for k, v in rule_data.__dict__.items() if not k.startswith("_")}

        raise ValueError(f"Cannot normalize rule data of type {type(rule_data).__name__}")

    def get_validator_info(self) -> dict[str, Any]:
        """Get information about validators in the gateway.

        Returns:
            Dictionary with validator information
        """
        if not isinstance(self._validators, CompositeValidator):
            return {}

        return {
            "validators": [v.validator_name for v in self._validators.validators],
            "count": len(self._validators.validators),
        }
