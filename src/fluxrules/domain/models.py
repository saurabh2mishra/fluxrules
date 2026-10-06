from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any
from uuid import uuid4

Fact = dict[str, Any]


# Rule Lifecycle Enums


class RuleStatus(Enum):
    """Rule lifecycle state."""

    DRAFT = "draft"
    PENDING_APPROVAL = "pending_approval"
    ACTIVE = "active"
    DEPRECATED = "deprecated"
    ARCHIVED = "archived"
    SUSPENDED = "suspended"


class ChangeReason(Enum):
    """Why a rule was changed."""

    INITIAL_CREATION = "initial_creation"
    BUG_FIX = "bug_fix"
    PERFORMANCE = "performance"
    COMPLIANCE = "compliance"
    BUSINESS_CHANGE = "business_change"
    DEPRECATION = "deprecation"
    OTHER = "other"


# Core Domain Models


@dataclass(slots=True, frozen=True)
class RuleCondition:
    fact: str
    operator: str
    value: Any

    def __post_init__(self) -> None:
        from fluxrules.engine.operators import VALID_OPERATORS

        if self.operator not in VALID_OPERATORS:
            raise ValueError(
                f"Unknown operator '{self.operator}'. Valid: {sorted(VALID_OPERATORS)}"
            )


class ConditionView(tuple):  # type: ignore[type-arg]
    """A flat conjunction of :class:`RuleCondition`, plus its provenance.

    A plain tuple could not answer the one question that matters when
    rebuilding a DSL from it: *were these leaves originally joined by AND?*
    Flattening ``OR(a, b)`` yields exactly the same two leaves as ``AND(a, b)``,
    so a consumer that reconstructs a tree from the tuple turns an OR into an
    AND - a stricter rule that fires less often, with nothing raised and no
    row that looks wrong.

    ``lossy`` records that the leaves came from a node the flat view cannot
    express (``or`` / ``not`` / nesting under them). It is a ``tuple``
    subclass so every existing consumer - iteration, ``len``, truthiness,
    indexing - keeps working unchanged; only code that reconstructs logic
    needs to consult the flag.
    """

    def __new__(cls, conditions=(), *, lossy: bool = False) -> ConditionView:
        self = super().__new__(cls, conditions)
        self.lossy = lossy
        return self

    lossy: bool

    def __repr__(self) -> str:
        return f"ConditionView({tuple(self)!r}, lossy={self.lossy})"


@dataclass(slots=True, frozen=True)
class EngineRule:
    """Internal engine representation of a rule.

    Immutable, parsed form used by the reference evaluator and persistence
    mappers. The canonical, public rule type is
    :class:`fluxrules.domain.unified_rule.Rule`; obtain this form from it via
    ``Rule.to_engine_rule()``.

    ``condition_dsl`` is the **authoritative representation of rule logic**: the
    full condition tree, preserving ``AND`` / ``OR`` / ``NOT`` / nesting, leaf
    operators and values. It is always present after construction, so nothing
    downstream has to reconstruct semantics from a lossy flat view.

    ``conditions`` is a **derived** flat conjunction of the tree's leaves, kept
    only for backward-compatible consumers (the reference evaluator's simple
    path and structural validators). It is always re-derived from
    ``condition_dsl`` so the two can never disagree, and it cannot express
    ``OR`` / ``NOT`` / nesting, so it must never be treated as authoritative.

    Construction accepts either ``condition_dsl`` (preferred) or a flat
    ``conditions`` tuple (for the native-format path that has no tree). When
    only ``conditions`` is given, the authoritative tree is synthesised from
    it; a flat conjunction round-trips faithfully. When both are given,
    ``condition_dsl`` wins and ``conditions`` is re-derived from it.
    """

    id: int
    name: str
    conditions: tuple[RuleCondition, ...] = ()
    actions: tuple[str, ...] = ()
    priority: int = 0
    group: str = ""
    description: str = ""
    enabled: bool = True
    created_at: str | None = None
    updated_at: str | None = None
    # Excluded from ``hash`` because a dict is unhashable; it stays part of
    # equality, so two rules with different logic remain unequal.
    condition_dsl: dict[str, Any] | None = field(default=None, hash=False)

    def __post_init__(self) -> None:
        if self.condition_dsl is None:
            # No tree given: synthesise the authoritative one from the flat
            # conjunction so every EngineRule always carries a complete,
            # evaluable tree - never a bare, lossy tuple.
            from fluxrules.domain.dsl.evaluator import conditions_to_dsl

            object.__setattr__(self, "condition_dsl", conditions_to_dsl(self.conditions))
        else:
            # The tree is authoritative; re-derive the flat view from it so the
            # two never diverge. Extraction is silent here - the loud
            # lossy-view warning belongs at the public ``Rule.conditions``
            # boundary, not at internal engine-rule construction.
            import warnings

            from fluxrules.domain.factory import _extract_conditions_from_dsl

            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                object.__setattr__(
                    self,
                    "conditions",
                    _extract_conditions_from_dsl(self.condition_dsl),
                )

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> EngineRule:
        """Create an ``EngineRule`` from a dictionary carrying ``condition_dsl``.

        The DSL tree is the authoritative logic and is passed through verbatim,
        so ``OR`` / ``NOT`` / nesting survive.
        """
        return cls(
            id=data.get("id", 0),
            name=data.get("name", ""),
            actions=(str(data["action"]),) if data.get("action") else (),
            priority=data.get("priority", 0),
            group=data.get("group", ""),
            description=data.get("description", ""),
            enabled=data.get("enabled", True),
            created_at=data.get("created_at"),
            updated_at=data.get("updated_at"),
            condition_dsl=data.get("condition_dsl"),
        )


@dataclass(slots=True, frozen=True)
class Ruleset:
    """A named group of rules for evaluation.

    The ``group`` field is the primary identifier (replaces the old ``id``/``name`` pair).
    """

    group: str
    rules: tuple[EngineRule, ...] = ()

    def __hash__(self) -> int:
        return hash(self.group)


@dataclass(slots=True)
class EvaluationResult:
    """The single result type for every FluxRules evaluation path.

    One type is returned by the top-level :func:`fluxrules.evaluate`, by
    :meth:`BaseEngine.evaluate <fluxrules.engine.base.BaseEngine.evaluate>`, and
    by the reference evaluator, so a caller never has to ask which shape it
    received. ``fluxrules.engine.infrastructure.EvaluationResult`` is a re-export
    of this class, not a second one.

    ``fired_rules`` is the answer to "what matched". It is the only field that
    ever means that; there is deliberately no ``matched_rule_ids``, because that
    name previously meant *fired* on one result type and *considered* on the
    other.

    Attributes:
        fired_rules: IDs of the rules that actually matched, highest priority
            first. This is the result.
        actions: Actions collected from every fired rule, in fire order.
        ruleset_group: The evaluated ruleset's group name. Set by the service
            layer; ``""`` when an engine is driven directly.
        trace: Per-rule evaluation trace. Populated by the reference evaluator.
        execution_id: Correlation ID for this evaluation, used to look the
            result back up via :func:`fluxrules.explain`.
        candidate_rule_ids: IDs the engine's discovery prefilter *considered*,
            before conditions were fully evaluated. Always a superset of
            ``fired_rules`` and never a statement about matching. Empty on
            paths that evaluate every rule linearly.
        rules_by_domain: Fired rule IDs grouped by their ``domain``.
        rules_by_tag: Fired rule IDs grouped by tag.
        fired_segments: Segment IDs touched during evaluation.
        latency_ms: Measured evaluation latency in milliseconds.
        engine_type: Name of the concrete engine class that produced this.
        explanations: Per-rule human-readable reason a rule fired.
    """

    # The result. What matched.
    fired_rules: list[int] = field(default_factory=list)
    actions: list[str] = field(default_factory=list)

    # Execution record, written by the service layer.
    ruleset_group: str = ""
    trace: list[dict[str, Any]] = field(default_factory=list)
    execution_id: str = field(default_factory=lambda: str(uuid4()))

    # Engine diagnostics. Left empty by non-engine evaluation paths.
    candidate_rule_ids: list[int] = field(default_factory=list)
    rules_by_domain: dict[str, list[int]] = field(default_factory=dict)
    rules_by_tag: dict[str, list[int]] = field(default_factory=dict)
    fired_segments: list[str] = field(default_factory=list)
    latency_ms: float = 0.0
    engine_type: str = ""
    explanations: dict[int, str] = field(default_factory=dict)
