"""Fluent API for building rules safely.

Provides type-safe rule construction with compile-time validation.
All conditions are parsed and validated at build time, not runtime.

Usage:
    from fluxrules.domain.rule_builder import RuleBuilder
    from fluxrules.domain.models import RuleStatus

    rule = (
        RuleBuilder(rule_id=1)
        .name("High Value Transaction Alert")
        .description("Flag transactions over $10,000")
        .group("fraud_detection")
        .priority(10)
        .condition({
            "type": "condition",
            "field": "amount",
            "op": ">",
            "value": 10000,
        })
        .action("flag_for_review")
        .action("notify_compliance")
        .status(RuleStatus.DRAFT)
        .build()
    )
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fluxrules.domain.dsl.parser import DSLParser
from fluxrules.domain.models import (
    ChangeReason,
    EngineRule,
    RuleStatus,
)
from fluxrules.domain.unified_rule import Rule
from fluxrules.exceptions import RuleValidationError
from fluxrules.utils.id_generators import RuleIDGenerator


class ConditionBuilder:
    """Build condition DSL with type checking.

    Usage:
        cb = ConditionBuilder()
        cb.condition("age", ">", 18)
        cb.condition("status", "==", "active")
        dsl = cb.build()  # Returns validated DSL dict
    """

    def __init__(self) -> None:
        self._nodes: list[dict[str, Any]] = []

    def condition(
        self,
        field: str,
        operator: str,
        value: Any,
    ) -> ConditionBuilder:
        """Add a leaf condition.

        Args:
            field: Fact field name.
            operator: Comparison operator (==, >, <, in, etc.)
            value: Value to compare against.

        Returns:
            Self for chaining.

        Raises:
            RuleValidationError: If field or operator is empty.
        """
        if not field or not operator:
            raise RuleValidationError("Field and operator required")

        self._nodes.append(
            {
                "type": "condition",
                "field": field,
                "op": operator,
                "value": value,
            }
        )
        return self

    def and_group(self, *conditions: dict[str, Any]) -> ConditionBuilder:
        """Create AND group from multiple condition dicts.

        Args:
            conditions: Condition DSL dicts to AND together.

        Returns:
            Self for chaining.
        """
        self._nodes.append(
            {
                "type": "group",
                "logic": "AND",
                "children": list(conditions),
            }
        )
        return self

    def or_group(self, *conditions: dict[str, Any]) -> ConditionBuilder:
        """Create OR group from multiple condition dicts.

        Args:
            conditions: Condition DSL dicts to OR together.

        Returns:
            Self for chaining.
        """
        self._nodes.append(
            {
                "type": "group",
                "logic": "OR",
                "children": list(conditions),
            }
        )
        return self

    def build(self) -> dict[str, Any]:
        """Build the condition DSL.

        Returns:
            Validated condition DSL dict.

        Raises:
            RuleValidationError: If no conditions defined or validation fails.
        """
        if not self._nodes:
            raise RuleValidationError("No conditions defined")

        # Parse to validate
        parser = DSLParser()
        for node in self._nodes:
            parser.parse(node)

        return (
            self._nodes[0]
            if len(self._nodes) == 1
            else {
                "type": "group",
                "logic": "AND",
                "children": self._nodes,
            }
        )


class RuleBuilder:
    """Fluent builder for rules.

    Validates all inputs at build time, ensuring only valid rules
    are constructed.

    Usage:
        rule = (
            RuleBuilder(1)
            .name("Adult Check")
            .condition({"type": "condition", "field": "age", "op": ">", "value": 18})
            .action("allow_access")
            .build()
        )
    """

    def __init__(
        self,
        rule_id: int | str | None = None,
        *,
        id_generator: RuleIDGenerator | None = None,
        persist: bool = False,
    ) -> None:
        """Initialize builder with rule ID.

        Args:
            rule_id: Unique identifier for the rule. If ``None``, the built
                :class:`~fluxrules.Rule` assigns one from the same shared
                generator every other authoring path uses, so IDs never
                collide between built and directly-constructed rules.
            id_generator: Optional :class:`RuleIDGenerator` to allocate the ID
                from instead, when *rule_id* is ``None``.
            persist: Store the built rule in the database and adopt its ID
                (default: False, matching :class:`~fluxrules.Rule`).
        """
        # A builder with no explicit ID defers to ``Rule``'s own generator
        # rather than spinning up a second one. Two independent sequential
        # generators both start at 1, so allocating here produced duplicate IDs
        # as soon as a built rule was mixed with a directly-constructed one.
        if rule_id is None and id_generator is not None:
            rule_id = id_generator.next_id()
        self._rule_id = rule_id
        self._id_generator = id_generator
        self._persist = persist
        self._name: str | None = None
        self._priority: int = 0
        self._group: str = ""
        self._description: str = ""
        self._enabled: bool = True
        self._status: RuleStatus = RuleStatus.DRAFT
        self._condition_dsl: dict[str, Any] | None = None
        self._actions: list[str] = []
        self._tags: set[str] = set()
        self._created_by: str = "system"
        self._approved_by: str | None = None
        self._approval_date: datetime | None = None
        self._change_reason: ChangeReason = ChangeReason.INITIAL_CREATION
        self._change_request_id: str | None = None

    def name(self, name: str) -> RuleBuilder:
        """Set rule name.

        Args:
            name: Human-readable rule name.

        Returns:
            Self for chaining.
        """
        self._name = name
        return self

    def priority(self, priority: int) -> RuleBuilder:
        """Set rule priority (higher = evaluated first).

        Args:
            priority: Non-negative integer priority.

        Returns:
            Self for chaining.

        Raises:
            RuleValidationError: If priority is negative or not an int.
        """
        if not isinstance(priority, int) or priority < 0:
            raise RuleValidationError("Priority must be non-negative integer")
        self._priority = priority
        return self

    def group(self, group: str) -> RuleBuilder:
        """Set rule group/domain.

        Args:
            group: Group name for categorization.

        Returns:
            Self for chaining.
        """
        self._group = group
        return self

    def description(self, description: str) -> RuleBuilder:
        """Set rule description.

        Args:
            description: Human-readable description.

        Returns:
            Self for chaining.
        """
        self._description = description
        return self

    def persist(self, enabled: bool = True) -> RuleBuilder:
        """Enable or disable persistence for the built rule.

        Args:
            enabled: Whether to store the built rule in the database.

        Returns:
            Self for chaining.
        """
        self._persist = enabled
        return self

    def enabled(self, enabled: bool) -> RuleBuilder:
        """Set enabled state.

        Args:
            enabled: Whether rule should be evaluated.

        Returns:
            Self for chaining.
        """
        self._enabled = enabled
        return self

    def status(self, status: RuleStatus) -> RuleBuilder:
        """Set rule lifecycle status.

        Args:
            status: RuleStatus enum value.

        Returns:
            Self for chaining.
        """
        self._status = status
        return self

    def condition(self, condition_dsl: dict[str, Any]) -> RuleBuilder:
        """Set condition DSL (validated at build time).

        Args:
            condition_dsl: Condition DSL dict.

        Returns:
            Self for chaining.

        Raises:
            DSLParseError: If condition DSL is invalid.
        """
        # Validate by parsing
        parser = DSLParser()
        parser.parse(condition_dsl)
        self._condition_dsl = condition_dsl
        return self

    def action(self, action: str) -> RuleBuilder:
        """Add an action to execute when rule matches.

        Args:
            action: Action name string.

        Returns:
            Self for chaining.

        Raises:
            RuleValidationError: If action is empty.
        """
        if not action:
            raise RuleValidationError("Action cannot be empty")
        self._actions.append(action)
        return self

    def tag(self, *tags: str) -> RuleBuilder:
        """Add tags for categorization.

        Args:
            tags: Tag strings.

        Returns:
            Self for chaining.
        """
        self._tags.update(tags)
        return self

    def created_by(self, user: str) -> RuleBuilder:
        """Set creator.

        Args:
            user: User ID or name.

        Returns:
            Self for chaining.
        """
        self._created_by = user
        return self

    def approved_by(self, user_id: str, approval_date: datetime | None = None) -> RuleBuilder:
        """Mark rule as approved.

        Args:
            user_id: Approver's ID.
            approval_date: When approved. Defaults to now.

        Returns:
            Self for chaining.
        """
        self._approved_by = user_id
        self._approval_date = approval_date or datetime.now(timezone.utc)
        self._status = RuleStatus.ACTIVE
        return self

    def change_reason(self, reason: ChangeReason) -> RuleBuilder:
        """Set reason for change.

        Args:
            reason: ChangeReason enum value.

        Returns:
            Self for chaining.
        """
        self._change_reason = reason
        return self

    def change_request(self, request_id: str) -> RuleBuilder:
        """Associate with a change request.

        Args:
            request_id: External change request ID.

        Returns:
            Self for chaining.
        """
        self._change_request_id = request_id
        return self

    def build(self) -> Rule:
        """Build the canonical :class:`~fluxrules.Rule`.

        Returns the same public ``Rule`` type that every other authoring path
        produces, so the result can be handed straight to
        ``engine.load_rules()`` or :func:`fluxrules.evaluate` with no
        conversion step.

        Returns:
            A validated :class:`~fluxrules.Rule`.

        Raises:
            RuleValidationError: If name or condition is missing.
        """
        if not self._name:
            raise RuleValidationError("Rule name is required")
        if self._condition_dsl is None:
            raise RuleValidationError("Rule condition is required")

        return Rule(
            id=int(self._rule_id) if isinstance(self._rule_id, str) else self._rule_id,
            name=self._name,
            condition_dsl=self._condition_dsl,
            actions=tuple(self._actions),
            priority=self._priority,
            domain=self._group or "default",
            description=self._description,
            enabled=self._enabled,
            tags=frozenset(self._tags),
            persist=self._persist,
        )

    def build_engine_rule(self) -> EngineRule:
        """Build the internal ``EngineRule`` representation.

        The escape hatch for the persistence mappers and the reference
        evaluator, which work with parsed condition tuples. Application code
        wants :meth:`build`.
        """
        return self.build().to_engine_rule(group=self._group or None)

    def to_dict(self) -> dict[str, Any]:
        """Build the canonical rule mapping (id, name, priority, condition_dsl, action).

        Returns:
            The dict shape accepted by rule ingestion and ``Rule(**data)``.

        Raises:
            RuleValidationError: If name or condition is missing.
        """
        if not self._name:
            raise RuleValidationError("Rule name is required")
        if self._condition_dsl is None:
            raise RuleValidationError("Rule condition is required")

        return {
            "id": int(self._rule_id) if isinstance(self._rule_id, str) else self._rule_id,
            "name": self._name,
            "priority": self._priority,
            "condition_dsl": self._condition_dsl,
            "action": self._actions[0] if self._actions else "",
            "enabled": self._enabled,
        }
