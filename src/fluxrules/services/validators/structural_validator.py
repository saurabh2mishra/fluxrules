"""Structural validator - validates DSL syntax and required fields."""

from __future__ import annotations

from typing import Any

from .base import ValidationResult, Validator

#: Node types that hold a list of child nodes. ``and``/``or`` are the shapes the
#: engines evaluate; ``group``/``composite`` are the equivalent authoring
#: shapes. ``AND``/``OR`` appear in older hand-written rules. All of them must
#: be recursed into - a type missing here is not merely unvalidated, it hides
#: its entire subtree from validation.
_BOOLEAN_NODE_TYPES = frozenset({"group", "composite", "and", "or", "AND", "OR"})


class StructuralValidator(Validator):
    """Validates DSL structure and required fields.

    Checks:
    - Required fields are present
    - DSL has valid structure (type, operators, etc.)
    - Field types are correct
    """

    REQUIRED_FIELDS = {"name", "condition_dsl", "action"}

    def validate(self, rule_data: dict[str, Any]) -> ValidationResult:
        """Validate rule structure."""
        result = ValidationResult()

        # Check required fields
        for field in self.REQUIRED_FIELDS:
            if field not in rule_data or rule_data[field] is None:
                result.add_error(
                    "missing_required_field",
                    f"Required field '{field}' is missing or None",
                    field=field,
                )

        # Check name constraints
        if rule_data.get("name"):
            name = rule_data["name"]
            if not isinstance(name, str):
                result.add_error(
                    "invalid_name_type",
                    f"Name must be string, got {type(name).__name__}",
                    field="name",
                )
            elif len(name) > 255:
                result.add_error(
                    "name_too_long",
                    f"Name must be <= 255 characters, got {len(name)}",
                    field="name",
                )
            elif len(name) < 1:
                result.add_error(
                    "name_too_short",
                    "Name must be at least 1 character",
                    field="name",
                )

        # Check condition_dsl structure
        if rule_data.get("condition_dsl"):
            condition = rule_data["condition_dsl"]
            if not isinstance(condition, dict):
                result.add_error(
                    "condition_dsl_not_dict",
                    f"condition_dsl must be dict, got {type(condition).__name__}",
                    field="condition_dsl",
                )
            else:
                # Validate DSL structure
                self._validate_dsl_structure(condition, result)

        # Check priority constraints
        if "priority" in rule_data and rule_data["priority"] is not None:
            try:
                priority = int(rule_data["priority"])
                if priority < 0:
                    result.add_error(
                        "negative_priority",
                        "Priority cannot be negative",
                        field="priority",
                    )
            except (ValueError, TypeError):
                result.add_error(
                    "invalid_priority_type",
                    f"Priority must be integer, got {type(rule_data['priority']).__name__}",
                    field="priority",
                )

        # Check enabled field
        if "enabled" in rule_data and rule_data["enabled"] is not None:
            if not isinstance(rule_data["enabled"], bool):
                result.add_warning(
                    "enabled_not_bool",
                    f"'enabled' should be boolean, got {type(rule_data['enabled']).__name__}",
                    field="enabled",
                )

        return result

    def _validate_dsl_structure(self, condition: dict[str, Any], result: ValidationResult) -> None:
        """Validate DSL structure recursively."""
        if "type" not in condition:
            result.add_error(
                "dsl_missing_type",
                "DSL condition must have 'type' field",
                field="condition_dsl",
            )
            return

        condition_type = condition.get("type")

        if condition_type == "condition":
            # Single condition: field, op, value
            required = {"field", "op", "value"}
            for field in required:
                if field not in condition:
                    result.add_error(
                        f"dsl_missing_{field}",
                        f"Condition DSL must have '{field}' for type 'condition'",
                        field="condition_dsl",
                    )

            # Validate operator
            if "op" in condition:
                # Sourced from the engine rather than hardcoded: a duplicated
                # list drifts, and this one had. It was missing the nine word
                # -form operators the engines accept (eq, gt, gte, lt, lte, ne,
                # regex, starts_with, ends_with), so a valid rule using them
                # was rejected outright by the strict gateway.
                from fluxrules.engine.operators import VALID_OPERATORS

                if condition["op"] not in VALID_OPERATORS:
                    result.add_error(
                        "invalid_operator",
                        f"Invalid operator: {condition['op']}. "
                        f"Must be one of: {sorted(VALID_OPERATORS)}",
                        field="condition_dsl",
                    )

        elif condition_type in _BOOLEAN_NODE_TYPES:
            # ``and``/``or`` are what the engines evaluate; ``group``/
            # ``composite`` are the equivalent authoring shapes, and children
            # live under either "children" or "conditions" depending on which
            # producer wrote the tree. Recognising only "group"/"children" made
            # every other shape fall through to the `unknown` branch below,
            # which returns without inspecting the subtree - so nothing inside
            # an `and` node was ever validated at all.
            children = condition.get("children") or condition.get("conditions") or []
            if not children:
                result.add_error(
                    "dsl_missing_children",
                    f"Group DSL (type '{condition_type}') must have non-empty "
                    "'children' (or 'conditions')",
                    field="condition_dsl",
                )
                return

            # Recursively validate children
            for idx, child in enumerate(children):
                if not isinstance(child, dict):
                    result.add_error(
                        "dsl_child_not_dict",
                        f"Child {idx} in group is not a dict",
                        field="condition_dsl",
                    )
                else:
                    self._validate_dsl_structure(child, result)

        elif condition_type == "not":
            # ``not`` holds a single child, spelled "condition" by the strict
            # authoring shape and "children" by the engine shape.
            child = condition.get("condition")
            children = condition.get("children") or ([child] if child else [])
            if not children:
                result.add_error(
                    "dsl_missing_children",
                    "NOT DSL must have a 'condition' (or 'children')",
                    field="condition_dsl",
                )
                return
            for child_node in children:
                if isinstance(child_node, dict):
                    self._validate_dsl_structure(child_node, result)

        else:
            result.add_warning(
                "unknown_dsl_type",
                f"Unknown DSL type: {condition_type}",
                field="condition_dsl",
            )

    @property
    def validator_name(self) -> str:
        """Return validator name."""
        return "StructuralValidator"
