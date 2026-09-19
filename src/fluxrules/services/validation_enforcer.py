"""Validation enforcer - applies validation decisions based on mode."""

from __future__ import annotations

import logging
from typing import Any

from fluxrules.services.validators import ValidationResult

logger = logging.getLogger(__name__)


class ValidationEnforcer:
    """Enforces validation decisions based on validation mode.

    Provides consistent enforcement logic for:
    - "strict" mode: Block on any error
    - "warning" mode: Log warnings but allow
    - "skip" mode: No validation
    """

    @staticmethod
    def enforce(
        result: ValidationResult,
        mode: str = "strict",
        rule_name: str | None = None,
    ) -> None:
        """Enforce validation based on mode and result.

        Args:
            result: ValidationResult to enforce
            mode: Enforcement mode ("strict", "warning", "skip")
            rule_name: Name of rule being validated (for logging)

        Raises:
            ValidationException: If mode=="strict" and errors found
        """
        if mode == "skip":
            return  # No enforcement

        rule_prefix = f"[{rule_name}] " if rule_name else ""

        # Check for errors
        errors = result.get_errors()
        if errors and mode == "strict":
            from fluxrules.services.validation_gateway import ValidationException

            error_lines = [f"  - {issue.message}" for issue in errors]
            message = f"{rule_prefix}Rule validation failed:\n" + "\n".join(error_lines)
            logger.error(message)
            raise ValidationException(message, result)

        # Log warnings
        warnings = result.get_warnings()
        if warnings:
            warning_lines = [f"  - {issue.message}" for issue in warnings]
            message = f"{rule_prefix}Rule validation warnings:\n" + "\n".join(warning_lines)

            if mode == "strict":
                logger.warning(message)
            elif mode == "warning":
                logger.warning(message)

    @staticmethod
    def get_decision(
        result: ValidationResult,
        mode: str = "strict",
    ) -> dict[str, Any]:
        """Get enforcement decision details.

        Args:
            result: ValidationResult to evaluate
            mode: Enforcement mode

        Returns:
            Dictionary with decision details
        """
        decision = {
            "mode": mode,
            "errors": len(result.get_errors()),
            "warnings": len(result.get_warnings()),
            "should_proceed": True,
            "reason": "No issues found",
        }

        if result.has_errors():
            if mode == "strict":
                decision["should_proceed"] = False
                decision["reason"] = "Blocking errors found in strict mode"
            elif mode == "warning":
                decision["reason"] = "Errors found but allowed in warning mode"

        elif result.has_warnings():
            decision["reason"] = f"{len(result.get_warnings())} warnings found"

        return decision

    @staticmethod
    def get_report_summary(
        result: ValidationResult,
        rule_name: str | None = None,
    ) -> str:
        """Get human-readable validation report summary.

        Args:
            result: ValidationResult to summarize
            rule_name: Name of rule (optional)

        Returns:
            Human-readable summary string
        """
        rule_prefix = f"Rule '{rule_name}': " if rule_name else "Validation: "

        if not result.issues:
            return f"{rule_prefix}✅ No issues"

        errors = result.get_errors()
        warnings = result.get_warnings()

        parts = [rule_prefix]

        if errors:
            parts.append(f"❌ {len(errors)} error(s)")
        if warnings:
            parts.append(f"⚠️  {len(warnings)} warning(s)")

        summary = " | ".join(parts)

        # Add details
        if errors:
            error_details = "\n".join([f"  - {e.message}" for e in errors[:3]])
            if len(errors) > 3:
                error_details += f"\n  ... and {len(errors) - 3} more"
            summary += f"\n{error_details}"

        if warnings:
            warning_details = "\n".join([f"  - {w.message}" for w in warnings[:3]])
            if len(warnings) > 3:
                warning_details += f"\n  ... and {len(warnings) - 3} more"
            summary += f"\n{warning_details}"

        return summary
