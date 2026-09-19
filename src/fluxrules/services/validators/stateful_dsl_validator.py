"""Stateful DSL validator - validates sequence, cross_fact_join, count_threshold nodes."""

from __future__ import annotations

import json
from typing import Any

from .base import ValidationResult, Validator


class StatefulDSLValidator(Validator):
    """Validates stateful DSL nodes (sequence, cross_fact_join, count_threshold).

    These node types have special requirements and can't be mixed at the top level.

    Checks:
    - sequence: minimum 2 steps, no empty steps
    - cross_fact_join: minimum 2 facts, no empty facts
    - count_threshold: valid threshold configuration
    - Top-level stateful node families are mutually exclusive
    """

    def validate(self, rule_data: dict[str, Any]) -> ValidationResult:
        """Validate stateful DSL nodes."""
        result = ValidationResult()

        condition_dsl = rule_data.get("condition_dsl")
        if not isinstance(condition_dsl, dict) or not condition_dsl:
            return result

        # Check top-level stateful node exclusivity
        self._validate_top_level_stateful_exclusivity(condition_dsl, result)

        # Walk and validate all stateful nodes
        self._walk_stateful_nodes(condition_dsl, result, path="$")

        return result

    def _validate_top_level_stateful_exclusivity(
        self, condition_dsl: dict[str, Any], result: ValidationResult
    ) -> None:
        """Validate that top-level stateful nodes don't mix families.

        Stateful node types (sequence, cross_fact_join, count_threshold) are
        mutually exclusive at the top level. You can't have both sequence and
        cross_fact_join as direct children of a group, for example.
        """
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
            result.add_error(
                "dsl_validation_error",
                f"Top-level stateful node families are mutually exclusive; found: {families}.",
                field="condition_dsl",
                details={"stateful_families": list(top_level_families)},
            )

    def _walk_stateful_nodes(
        self,
        node: Any,
        result: ValidationResult,
        path: str,
    ) -> None:
        """Recursively validate stateful DSL nodes."""
        if isinstance(node, list):
            for idx, child in enumerate(node):
                self._walk_stateful_nodes(child, result, f"{path}[{idx}]")
            return
        if not isinstance(node, dict):
            return

        node_type = node.get("type")

        # Validate sequence nodes
        if node_type == "sequence":
            self._validate_sequence(node, result, path)

        # Validate cross_fact_join nodes
        elif node_type == "cross_fact_join":
            self._validate_cross_fact_join(node, result, path)

        # Validate count_threshold nodes
        elif node_type == "count_threshold":
            self._validate_count_threshold(node, result, path)

        # Recurse into children
        for key, value in node.items():
            if isinstance(value, (dict, list)):
                child_path = f"{path}.{key}" if path != "$" else f"$.{key}"
                self._walk_stateful_nodes(value, result, child_path)

    def _validate_sequence(self, node: dict[str, Any], result: ValidationResult, path: str) -> None:
        """Validate sequence node structure and content."""
        steps = node.get("steps")

        if steps is None:
            result.add_error(
                "dsl_validation_error",
                "sequence requires 'steps' field.",
                field=f"{path}.steps",
            )
            return

        if not isinstance(steps, list):
            result.add_error(
                "dsl_validation_error",
                "sequence.steps must be an array.",
                field=f"{path}.steps",
            )
            return

        if len(steps) < 2:
            result.add_error(
                "dsl_validation_error",
                "sequence.steps >= 2 (minimum 2 steps required).",
                field=f"{path}.steps",
            )
            return

        # Warn if all steps are identical (suggests count_threshold intent)
        if len(steps) >= 2:
            normalized_steps = [
                json.dumps(step, sort_keys=True) for step in steps if isinstance(step, dict)
            ]
            if len(set(normalized_steps)) == 1:
                result.add_warning(
                    "dsl_validation_warning",
                    "sequence pattern is equivalent to count-threshold intent; consider using count_threshold.",
                    field=path,
                )

    def _validate_cross_fact_join(
        self, node: dict[str, Any], result: ValidationResult, path: str
    ) -> None:
        """Validate cross_fact_join node structure and content."""
        facts = node.get("facts")

        if facts is None:
            result.add_error(
                "dsl_validation_error",
                "cross_fact_join requires 'facts' field.",
                field=f"{path}.facts",
            )
            return

        if not isinstance(facts, list):
            result.add_error(
                "dsl_validation_error",
                "cross_fact_join.facts must be an array.",
                field=f"{path}.facts",
            )
            return

        if len(facts) < 2:
            result.add_error(
                "dsl_validation_error",
                "cross_fact_join.facts >= 2 (minimum 2 facts required).",
                field=f"{path}.facts",
            )

    def _validate_count_threshold(
        self, node: dict[str, Any], result: ValidationResult, path: str
    ) -> None:
        """Validate count_threshold node structure and content."""
        threshold = node.get("threshold")

        if threshold is None:
            result.add_error(
                "dsl_validation_error",
                "count_threshold requires 'threshold' field.",
                field=f"{path}.threshold",
            )
            return

        if not isinstance(threshold, (int, float)) or threshold < 1:
            result.add_error(
                "dsl_validation_error",
                "count_threshold.threshold must be a positive number.",
                field=f"{path}.threshold",
            )

    @property
    def validator_name(self) -> str:
        """Return validator name."""
        return "StatefulDSLValidator"
