"""Domain-specific language abstract syntax tree.

Defines the AST nodes for FluxRules condition trees and the Visitor
interface for processing them. This decouples condition tree interpretation from
network building, allowing multiple visitors (compilation, validation,
optimization) to process the same tree.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any


class ConditionTreeNode(ABC):
    """Base class for all condition tree nodes."""

    @property
    @abstractmethod
    def node_type(self) -> str:
        """Unique identifier for this node type."""
        ...

    @abstractmethod
    def accept(self, visitor: ConditionTreeVisitor) -> Any:
        """Accept a visitor (double-dispatch)."""
        ...


class ConditionTreeVisitor(ABC):
    """Visitor pattern for condition tree traversal."""

    @abstractmethod
    def visit_condition(self, node: ConditionNode) -> Any:
        """Visit a leaf condition (field operator value)."""
        ...

    @abstractmethod
    def visit_group(self, node: GroupNode) -> Any:
        """Visit a group (AND/OR of multiple conditions)."""
        ...

    @abstractmethod
    def visit_not(self, node: NotNode) -> Any:
        """Visit a NOT node."""
        ...

    @abstractmethod
    def visit_exists(self, node: ExistsNode) -> Any:
        """Visit an EXISTS node."""
        ...

    @abstractmethod
    def visit_accumulate(self, node: AccumulateNode) -> Any:
        """Visit an ACCUMULATE node."""
        ...

    @abstractmethod
    def visit_sequence(self, node: SequenceNode) -> Any:
        """Visit a SEQUENCE node."""
        ...

    @abstractmethod
    def visit_cross_fact_join(self, node: CrossFactJoinNode) -> Any:
        """Visit a CROSS_FACT_JOIN node."""
        ...


# Concrete DSL Node Types


@dataclass(frozen=True)
class ConditionNode(ConditionTreeNode):
    """Leaf condition: field operator value."""

    field: str
    operator: str
    value: Any

    @property
    def node_type(self) -> str:
        return "condition"

    def accept(self, visitor: ConditionTreeVisitor) -> Any:
        return visitor.visit_condition(self)


@dataclass(frozen=True)
class GroupNode(ConditionTreeNode):
    """Group of conditions with AND/OR logic."""

    logic: str  # "AND" or "OR"
    children: tuple[ConditionTreeNode, ...]

    @property
    def node_type(self) -> str:
        return "group"

    def accept(self, visitor: ConditionTreeVisitor) -> Any:
        return visitor.visit_group(self)


@dataclass(frozen=True)
class NotNode(ConditionTreeNode):
    """Negation of a condition or group."""

    inner: ConditionTreeNode | None = None
    children: tuple[ConditionTreeNode, ...] = ()

    @property
    def node_type(self) -> str:
        return "not"

    def accept(self, visitor: ConditionTreeVisitor) -> Any:
        return visitor.visit_not(self)


@dataclass(frozen=True)
class ExistsNode(ConditionTreeNode):
    """Test for field existence or inner condition existence."""

    field: str | None = None
    inner: ConditionTreeNode | None = None

    @property
    def node_type(self) -> str:
        return "exists"

    def accept(self, visitor: ConditionTreeVisitor) -> Any:
        return visitor.visit_exists(self)


@dataclass(frozen=True)
class AccumulateNode(ConditionTreeNode):
    """Accumulate results from matching facts."""

    source: str | None = None
    field: str | None = None
    aggregate: str = "count"
    operator: str = "=="
    value: Any = None
    where: ConditionTreeNode | None = None

    @property
    def node_type(self) -> str:
        return "accumulate"

    def accept(self, visitor: ConditionTreeVisitor) -> Any:
        return visitor.visit_accumulate(self)


@dataclass(frozen=True)
class SequenceNode(ConditionTreeNode):
    """Sequence of facts in temporal order."""

    source: str | None = None
    steps: tuple[ConditionTreeNode, ...] = ()

    @property
    def node_type(self) -> str:
        return "sequence"

    def accept(self, visitor: ConditionTreeVisitor) -> Any:
        return visitor.visit_sequence(self)


@dataclass(frozen=True)
class CrossFactJoinNode(ConditionTreeNode):
    """Join facts from different sources via correlation field."""

    correlate_field: str

    @property
    def node_type(self) -> str:
        return "cross_fact_join"

    def accept(self, visitor: ConditionTreeVisitor) -> Any:
        return visitor.visit_cross_fact_join(self)
