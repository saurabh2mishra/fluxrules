"""Unified Rule class with Pydantic validation and automatic ID generation.

This is the canonical, public ``Rule`` type. It is the single class used across
every authoring path (YAML, REST API, ORM, CLI) and is what the modern
DSL-based PHREAK engine consumes via ``condition_dsl``.

For the reference evaluator and the persistence layer, which work with parsed
:class:`~fluxrules.domain.models.RuleCondition` tuples, use the ``conditions``
property (read-only) or :meth:`Rule.to_engine_rule` to obtain the internal
engine representation. Conversion is always explicit through those members, so
callers never need to guess which shape a rule is in.

This module provides a single Rule class that:
1. Uses Pydantic for strict type validation and fast failure
2. Auto-generates sequential IDs by default (user-overridable)
3. Works across all creation paths (YAML, REST API, ORM, CLI, etc.)
4. Provides a consistent interface for all rule creation patterns
5. Converts between formats (dict, JSON, YAML) and the engine representation

Key Design Decisions:
- ID is auto-generated but user can override if needed
- Pydantic v2 for strict validation with helpful error messages
- Serialization support for all major formats
- Domain + tags for rule discovery and organization
- Optional metadata for extensibility

Usage:
    # Simple rule with auto-generated ID
    rule = Rule(
        name="High Value Transaction",
        condition_dsl={"type": "condition", "field": "amount", "op": ">", "value": 1000},
        action="flag_for_review",
    )
    print(rule.id)  # Auto-generated sequential ID

    # Override ID if needed
    rule = Rule(
        id=42,
        name="My Rule",
        condition_dsl={...},
        action="flag",
    )

    # From dict (e.g., from YAML)
    rule = Rule(**row)  # Pydantic validation applied

    # To dict for serialization
    rule_dict = rule.model_dump()
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from fluxrules.utils.id_generators import RuleIDGenerator

if TYPE_CHECKING:
    from fluxrules.domain.models import EngineRule as DomainRule
    from fluxrules.domain.models import RuleCondition

logger = logging.getLogger(__name__)

# Global ID generator (can be overridden per-instance)
_default_id_generator = RuleIDGenerator(strategy="sequential")


class Rule(BaseModel):
    """Unified Rule class for all creation paths.

    Attributes:
        id: Unique rule identifier (auto-generated from DB if not provided)
        name: Human-readable rule name
        condition_dsl: Rule condition in DSL format (dict)
        action: Primary action; a compatibility view of ``actions[0]``
        actions: All actions to execute when the rule matches, in order
        priority: Execution priority (higher = evaluated first)
        enabled: Whether rule is active
        domain: Rule category/domain for discovery
        tags: Set of tags for organization and filtering
        metadata: Optional metadata for extensibility
        description: Human-readable description
        version: Rule version
        sla_latency_ms: Expected latency SLA in milliseconds
        created_at: Creation timestamp (ISO 8601), assigned by the persistence layer
        updated_at: Last update timestamp (ISO 8601), assigned by the persistence layer
        persist: Whether to persist this rule to database (default: True)

    Configuration:
        - Pydantic v2 with strict validation
        - Extra fields forbidden (strict)
        - Serialization support (JSON, dict, etc.)
        - Automatic persistence to database by default
    """

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    id: int | None = Field(
        default=None,
        description="Unique rule ID (auto-generated from DB if not provided)",
    )
    name: str = Field(..., min_length=1, max_length=255, description="Rule name")
    condition_dsl: dict[str, Any] = Field(..., description="Rule condition in DSL format")
    action: str = Field(
        default="",
        description=(
            "Primary action to execute when the rule matches. Kept for "
            "backwards compatibility; it is always ``actions[0]``."
        ),
    )
    actions: tuple[str, ...] = Field(
        default=(),
        description="All actions to execute when the rule matches, in order",
    )
    priority: int = Field(default=0, ge=0, description="Execution priority")
    enabled: bool = Field(default=True, description="Whether rule is active")
    domain: str = Field(default="default", description="Rule domain/category")
    tags: frozenset[str] = Field(default_factory=frozenset, description="Tags for organization")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Optional metadata")
    description: str = Field(default="", description="Rule description")
    version: str = Field(default="1.0", description="Rule version")
    sla_latency_ms: int = Field(default=100, ge=0, description="SLA latency in milliseconds")
    created_at: str | None = Field(
        default=None,
        description="Creation timestamp (ISO 8601), assigned by the persistence layer",
    )
    updated_at: str | None = Field(
        default=None,
        description="Last update timestamp (ISO 8601), assigned by the persistence layer",
    )
    persist: bool = Field(
        default=True,
        description="Whether to persist this rule to database (default: True)",
    )

    @field_validator("tags", mode="before")
    @classmethod
    def validate_tags(cls, v: Any) -> frozenset[str]:
        """Convert tags to frozenset."""
        if isinstance(v, frozenset):
            return v
        if isinstance(v, (list, set, tuple)):
            return frozenset(v)
        if isinstance(v, str):
            # Handle comma-separated string
            return frozenset(tag.strip() for tag in v.split(",") if tag.strip())
        if v is None:
            return frozenset()
        raise ValueError(f"Invalid tags type: {type(v)}")

    @field_validator("condition_dsl")
    @classmethod
    def validate_condition_dsl(cls, v: dict[str, Any]) -> dict[str, Any]:
        """Validate condition DSL structure."""
        if not isinstance(v, dict):
            raise ValueError("condition_dsl must be a dictionary")
        if not v:
            raise ValueError("condition_dsl cannot be empty")
        # Basic structure validation
        if "type" not in v:
            raise ValueError("condition_dsl must have 'type' field")

        # A structurally well-formed but *logically* empty tree - say
        # {"type": "and", "children": []} - passes every check above while
        # being unable to match anything. Caught here so authoring fails
        # immediately, at the point the author can still fix it.
        from fluxrules.domain.dsl.evaluator import has_logic

        if not has_logic(v):
            raise ValueError(
                "condition_dsl contains no conditions, so this rule could "
                "never fire. Add at least one condition, or give the rule an "
                "explicit always-true condition if it is meant to always apply."
            )
        return v

    @field_validator("actions", mode="before")
    @classmethod
    def validate_actions(cls, v: Any) -> tuple[str, ...]:
        """Coerce ``actions`` into a tuple of non-empty strings."""
        if v is None:
            return ()
        if isinstance(v, str):
            # A newline-joined string is how the ORM stores multiple actions.
            return tuple(a.strip() for a in v.split("\n") if a.strip())
        if isinstance(v, (list, tuple, set, frozenset)):
            return tuple(str(a) for a in v if str(a))
        raise ValueError(f"Invalid actions type: {type(v)}")

    @model_validator(mode="after")
    def sync_action_and_actions(self) -> Rule:
        """Keep the singular ``action`` and plural ``actions`` consistent.

        ``actions`` is canonical. ``action`` is a backwards-compatible view of
        the first element, so existing single-action code keeps working while
        multi-action rules round-trip through persistence without truncation.

        This runs *before* :meth:`auto_persist_if_enabled` (Pydantic executes
        ``mode="after"`` validators in definition order), so whatever is
        persisted already carries the full action list.
        """
        if self.actions and not self.action:
            object.__setattr__(self, "action", self.actions[0])
        elif self.action and not self.actions:
            object.__setattr__(self, "actions", (self.action,))
        elif self.action and self.actions and self.action != self.actions[0]:
            raise ValueError(
                f"Conflicting actions: action={self.action!r} but "
                f"actions[0]={self.actions[0]!r}. Set only one, or make "
                "'action' match the first element of 'actions'."
            )
        return self

    @model_validator(mode="after")
    def auto_persist_if_enabled(self) -> Rule:
        """Auto-generate ID and optionally persist to database.

        If persist=True (default), saves rule to database and gets DB-assigned ID.
        If persist=False, generates a local sequential ID.
        """
        # Skip persistence if ID already assigned (already persisted)
        if self.id is not None:
            return self

        # Handle persistence
        if self.persist:
            try:
                from fluxrules.persistence.persistence_manager import (
                    get_persistence_manager,
                )

                pm = get_persistence_manager()
                persisted_rule = pm.persist_rule(
                    self,
                    group=self.domain,
                )
                # Update self with persisted data (including DB-assigned ID)
                if persisted_rule.id is not None:
                    object.__setattr__(self, "id", persisted_rule.id)
                return self
            except Exception as e:
                logger.warning(
                    f"Failed to persist rule '{self.name}', falling back to local ID: {e}"
                )
                # Fall back to local ID generation
                # The generator may return a str id (e.g. uuid/hash strategy);
                # the field is typed int for the common sequential case.
                self.id = _default_id_generator.next_id()  # type: ignore[assignment]
        else:
            # Persistence disabled: generate local ID
            self.id = _default_id_generator.next_id()  # type: ignore[assignment]

        return self

    def model_dump(self, **kwargs: Any) -> dict[str, Any]:
        """Serialize to dictionary.

        Excludes internal 'persist' field from serialization.
        """
        # Exclude persist field from output (it's internal)
        kwargs.setdefault("exclude", set())
        if isinstance(kwargs["exclude"], set):
            kwargs["exclude"].add("persist")

        data = super().model_dump(**kwargs)
        # Ensure tags is serialized as list (more JSON-friendly)
        if isinstance(data.get("tags"), frozenset):
            data["tags"] = list(data["tags"])
        return data

    def model_dump_json(self, **kwargs: Any) -> str:
        """Serialize to JSON string."""
        return super().model_dump_json(**kwargs)

    @classmethod
    def model_validate_yaml(cls, data: dict[str, Any]) -> Rule:
        """Create Rule from YAML dict."""
        return cls(**data)

    def to_engine_dict(self) -> dict[str, Any]:
        """Convert to internal engine format."""
        return {
            "id": self.id,
            "name": self.name,
            "priority": self.priority,
            "condition_dsl": self.condition_dsl,
            "action": self.action,
            "actions": list(self.actions),
            "enabled": self.enabled,
            "domain": self.domain,
            "tags": self.tags,
        }

    @property
    def conditions(self) -> tuple[RuleCondition, ...]:
        """Parsed conditions derived from ``condition_dsl`` (read-only).

        The canonical representation is ``condition_dsl``. This view exposes the
        same ``RuleCondition`` tuple the reference evaluator and persistence layer
        expect, without duplicating the DSL as stored state.
        """
        from fluxrules.domain.factory import _extract_conditions_from_dsl

        return _extract_conditions_from_dsl(self.condition_dsl)

    def to_engine_rule(self, group: str | None = None) -> DomainRule:
        """Convert to the internal engine ``Rule`` representation.

        The reference evaluator and persistence mappers operate on parsed
        ``RuleCondition`` tuples and a tuple of action strings. This is the
        single explicit adapter from the canonical :class:`Rule` to that shape;
        callers should use it instead of inspecting a rule's attributes.
        """
        from fluxrules.domain.models import EngineRule as DomainRule

        return DomainRule(
            id=self.id if self.id is not None else 0,
            name=self.name,
            actions=self.actions,
            priority=self.priority,
            group=group if group is not None else self.domain,
            description=self.description,
            enabled=self.enabled,
            created_at=self.created_at,
            updated_at=self.updated_at,
            condition_dsl=self.condition_dsl,
        )

    @classmethod
    def from_engine_rule(
        cls,
        engine_rule: DomainRule,
        *,
        persist: bool = False,
        condition_dsl: dict[str, Any] | None = None,
        **overrides: Any,
    ) -> Rule:
        """Build a canonical :class:`Rule` from an internal ``EngineRule``.

        The inverse of :meth:`to_engine_rule`, completing the round trip needed
        by the persistence layer.

        ``EngineRule`` stores *parsed* conditions rather than the DSL, so the
        DSL is reconstructed: a single condition maps to a ``condition`` node,
        several to an ``AND`` group. That reconstruction is faithful for rules
        that originated as a flat conjunction, but it **cannot recover ``OR``
        or nested structure**, because that information is not present in the
        parsed tuple. Pass ``condition_dsl`` explicitly when the original DSL
        is known.

        ``persist`` defaults to ``False``: this converts an object that already
        exists in storage, so persisting again would duplicate it.
        """
        if condition_dsl is None:
            # Prefer the DSL the engine rule carried: it is the authoritative,
            # faithful source. An EngineRule always carries one now, so the
            # reconstruction below is only a fallback for foreign objects.
            condition_dsl = getattr(engine_rule, "condition_dsl", None)
        if condition_dsl is None:
            # Reconstructing from the flat tuple silently turns an OR into an
            # AND, so this is reached only when no tree exists at all.
            conditions = tuple(engine_rule.conditions)
            if len(conditions) == 1:
                c = conditions[0]
                condition_dsl = {
                    "type": "condition",
                    "field": c.fact,
                    "op": c.operator,
                    "value": c.value,
                }
            else:
                condition_dsl = {
                    "type": "group",
                    "op": "AND",
                    "children": [
                        {
                            "type": "condition",
                            "field": c.fact,
                            "op": c.operator,
                            "value": c.value,
                        }
                        for c in conditions
                    ],
                }

        data: dict[str, Any] = {
            "id": engine_rule.id,
            "name": engine_rule.name,
            "condition_dsl": condition_dsl,
            "actions": tuple(engine_rule.actions),
            "priority": engine_rule.priority,
            "domain": engine_rule.group or "default",
            "description": engine_rule.description,
            "enabled": engine_rule.enabled,
            "created_at": engine_rule.created_at,
            "updated_at": engine_rule.updated_at,
            "persist": persist,
        }
        data.update(overrides)
        return cls(**data)

    def __repr__(self) -> str:
        """String representation."""
        return (
            f"Rule(id={self.id}, name={self.name!r}, "
            f"priority={self.priority}, action={self.action!r})"
        )

    def __str__(self) -> str:
        """User-friendly string."""
        return f"{self.name} (ID: {self.id})"

    @classmethod
    def set_id_generator(cls, generator: RuleIDGenerator) -> None:
        """Set global ID generator for all Rule instances.

        Usage:
            config = DeploymentConfig(deployment_type=DeploymentType.MULTI_INSTANCE)
            gen = RuleIDGenerator.from_config(config)
            Rule.set_id_generator(gen)
        """
        global _default_id_generator
        _default_id_generator = generator
        logger.info(f"Rule ID generator set to: {generator.strategy.value}")
