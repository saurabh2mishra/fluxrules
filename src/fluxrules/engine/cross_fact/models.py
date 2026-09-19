"""Data model for the cross-fact join engine.

These types describe **multi-fact** rules - the shapes the single-fact
``PhreakEngine`` deliberately rejects (see ``scope_guard.py``). A
:class:`CrossFactRule` is an ordered list of :class:`Pattern` objects; the engine
holds many facts in working memory and matches *tuples* of facts that satisfy
both each pattern's **alpha** constraints (field vs. literal) and the cross-fact
**join** constraints (field vs. an earlier pattern's field).

This module is intentionally dependency-light: it is pure data + a tiny operator
alias map. All evaluation lives in :mod:`fluxrules.engine.cross_fact._engine`.
"""

from __future__ import annotations

from dataclasses import dataclass
from dataclasses import field as dc_field
from typing import Any

# Canonical-name -> symbol, so callers may write either ``"eq"`` or ``"=="``.
# ``operators.evaluate_operator`` only branches on the symbol forms.
_OP_ALIAS = {
    "eq": "==",
    "ne": "!=",
    "gt": ">",
    "gte": ">=",
    "lt": "<",
    "lte": "<=",
}


def normalize_op(op: str) -> str:
    """Return the symbol form of an operator (``"gt"`` -> ``">"``)."""
    return _OP_ALIAS.get(op, op)


@dataclass
class FactHandle:
    """A typed fact resident in beta working memory.

    Attributes:
        id: Monotonic, stable identity assigned at insert. Identity is preserved
            across :meth:`CrossFactEngine.update`, so truth maintenance can re-derive
            matches without callers re-keying.
        fact_type: The fact's type (``"Order"``, ``"Customer"``, …); patterns
            match on this.
        fields: The fact's attributes. Mutable so ``update`` can replace them in
            place while keeping ``id`` stable.
    """

    id: int
    fact_type: str
    fields: dict[str, Any]


@dataclass(frozen=True)
class AlphaConstraint:
    """A single-fact constraint: ``field <op> literal`` (e.g. ``amount > 100``)."""

    field: str
    op: str
    value: Any

    def __post_init__(self) -> None:
        object.__setattr__(self, "op", normalize_op(self.op))


@dataclass(frozen=True)
class JoinConstraint:
    """A cross-fact constraint: ``this.field <op> other_var.other_field``.

    Example: on a ``Customer`` pattern bound to ``c``, ``JoinConstraint("id",
    "==", "o", "customer_id")`` means ``c.id == o.customer_id`` where ``o`` is an
    earlier-bound ``Order``. Equality joins are **hash-indexed**; other operators
    fall back to a filtered scan.
    """

    this_field: str
    op: str
    other_var: str
    other_field: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "op", normalize_op(self.op))

    @property
    def is_equality(self) -> bool:
        return self.op == "=="


# Allen-style temporal relations supported by :class:`TemporalConstraint` (B-δ).
TEMPORAL_RELATIONS: frozenset[str] = frozenset({"within", "after", "before"})


@dataclass(frozen=True)
class TemporalConstraint:
    """A **temporal window** constraint (B-δ) between this fact and an earlier one.

    Relates this element's timestamp (``this_field``) to an already-bound
    pattern's timestamp (``other_var``.``other_field``) within ``window`` (in the
    same units as the timestamps - seconds, ms, whatever your data uses). With
    ``t = this.ts`` and ``o = other.ts``:

    - ``within``: ``abs(t - o) <= window`` - the two events are within ``window``
      of each other (order-independent).
    - ``after``:  ``0 <= t - o <= window`` - this happened **after** ``other``,
      no more than ``window`` later.
    - ``before``: ``0 <= o - t <= window`` - this happened **before** ``other``,
      no more than ``window`` earlier.

    ``this_field`` / ``other_field`` default to the engine's configured time field
    (``CrossFactEngine(time_field=…)``, default ``"ts"``) when left ``None``.

    Window expiration uses ``window`` to bound memory: a fact older than
    ``clock - window`` can never again satisfy this constraint and is auto-retracted.
    """

    other_var: str
    relation: str
    window: float
    this_field: str | None = None
    other_field: str | None = None

    def __post_init__(self) -> None:
        if self.relation not in TEMPORAL_RELATIONS:
            raise ValueError(
                f"unknown temporal relation {self.relation!r}; "
                f"expected one of {sorted(TEMPORAL_RELATIONS)}"
            )
        if self.window < 0:
            raise ValueError(f"temporal window must be >= 0, got {self.window!r}")


@dataclass
class Pattern:
    """One fact pattern within a :class:`CrossFactRule`.

    Attributes:
        var: Binding name (``"o"``) used by later patterns' join constraints.
        fact_type: Which fact type this pattern matches.
        constraints: Alpha constraints (field vs. literal). Accepts
            :class:`AlphaConstraint` or ``(field, op, value)`` tuples.
        joins: Cross-fact constraints referencing **earlier** patterns. Accepts
            :class:`JoinConstraint` or ``(this_field, op, other_var, other_field)``
            tuples.
        temporal: Temporal window constraints (B-δ) relating this fact's time to
            an earlier pattern's. Accepts :class:`TemporalConstraint` or
            ``(other_var, relation, window)`` tuples.
    """

    var: str
    fact_type: str
    constraints: list[AlphaConstraint] = dc_field(default_factory=list)
    joins: list[JoinConstraint] = dc_field(default_factory=list)
    temporal: list[TemporalConstraint] = dc_field(default_factory=list)

    def __post_init__(self) -> None:
        self.constraints = _coerce_constraints(self.constraints)
        self.joins = _coerce_joins(self.joins)
        self.temporal = _coerce_temporal(self.temporal)


@dataclass
class Exists:
    """A working-memory **quantifier** (B-γ): ``exists`` or ``not`` (absence).

    Unlike a :class:`Pattern`, a quantifier **binds no fact** and does not extend
    the match tuple - it merely *gates* whether the partial match survives, based
    on whether **any** fact of ``fact_type`` satisfies its alpha + join
    constraints against the already-bound facts.

    - ``negated=False`` (``exists``): survive iff **≥1** matching fact exists.
    - ``negated=True``  (``not``):    survive iff **0** matching facts exist.

    Because the engine recomputes a rule whenever a fact of a referenced type
    changes, a retraction that empties an ``exists`` (or fills a ``not``) flips
    the quantifier and correctly un-fires dependent activations.
    """

    fact_type: str
    constraints: list[AlphaConstraint] = dc_field(default_factory=list)
    joins: list[JoinConstraint] = dc_field(default_factory=list)
    temporal: list[TemporalConstraint] = dc_field(default_factory=list)
    negated: bool = False

    def __post_init__(self) -> None:
        self.constraints = _coerce_constraints(self.constraints)
        self.joins = _coerce_joins(self.joins)
        self.temporal = _coerce_temporal(self.temporal)


# Supported collection-aggregate functions (B-γ). ``count`` needs no field;
# ``collect`` returns the tuple of field values; the rest reduce numeric values.
AGG_FUNCTIONS: frozenset[str] = frozenset({"count", "sum", "avg", "min", "max", "collect"})


@dataclass
class Accumulate:
    """A collection **aggregate** (B-γ): reduce a set of facts to one value.

    Aggregates over **every** fact of ``fact_type`` that satisfies the alpha +
    join constraints (e.g. all of *this* customer's orders), binds the result to
    ``var``, and - if ``having`` is given - only survives when the aggregate
    satisfies that threshold.

    Attributes:
        var: Name the aggregate result is bound to (exposed on
            ``Activation.aggregates[var]``).
        fact_type: The collection's fact type.
        function: One of :data:`AGG_FUNCTIONS`.
        field: Field to reduce. Required for everything except ``count``.
        constraints: Alpha filter applied to each fact before aggregating.
        joins: Cross-fact filter referencing earlier-bound vars (e.g. aggregate
            only facts belonging to the bound customer).
        having: Optional ``(op, threshold)`` the aggregate must satisfy, e.g.
            ``(">=", 1000)``. ``None`` means "always survive" (pure projection).

    Note:
        The aggregate value is **terminal**: it is exposed for actions and the
        ``having`` test, but cannot itself be the target of a later pattern's
        join (joins reference *fact* fields, not scalar aggregates).
    """

    var: str
    fact_type: str
    function: str
    field: str | None = None
    constraints: list[AlphaConstraint] = dc_field(default_factory=list)
    joins: list[JoinConstraint] = dc_field(default_factory=list)
    temporal: list[TemporalConstraint] = dc_field(default_factory=list)
    having: tuple[str, Any] | None = None

    def __post_init__(self) -> None:
        if self.function not in AGG_FUNCTIONS:
            raise ValueError(
                f"unknown aggregate function {self.function!r}; "
                f"expected one of {sorted(AGG_FUNCTIONS)}"
            )
        if self.function != "count" and not self.field:
            raise ValueError(f"aggregate function {self.function!r} requires a 'field'")
        self.constraints = _coerce_constraints(self.constraints)
        self.joins = _coerce_joins(self.joins)
        self.temporal = _coerce_temporal(self.temporal)
        if self.having is not None:
            op, threshold = self.having
            self.having = (normalize_op(op), threshold)


# An element of a rule body: a binding pattern, a quantifier, or an aggregate.
def _coerce_constraints(items: list[Any]) -> list[AlphaConstraint]:
    return [c if isinstance(c, AlphaConstraint) else AlphaConstraint(*c) for c in items]


def _coerce_joins(items: list[Any]) -> list[JoinConstraint]:
    return [j if isinstance(j, JoinConstraint) else JoinConstraint(*j) for j in items]


def _coerce_temporal(items: list[Any]) -> list[TemporalConstraint]:
    return [t if isinstance(t, TemporalConstraint) else TemporalConstraint(*t) for t in items]


@dataclass
class CrossFactRule:
    """A multi-fact rule: an ordered list of :class:`Pattern` / :class:`Exists` /
    :class:`Accumulate` elements.

    A complete match binds one fact to every :class:`Pattern` such that all alpha
    and join constraints hold, every :class:`Exists` quantifier is satisfied, and
    every :class:`Accumulate` ``having`` threshold passes. The element order is
    the join order; an element's ``joins`` may only reference patterns bound
    **before** it.
    """

    id: int
    name: str
    patterns: list[Pattern]
    action: str = ""
    priority: int = 0

    def __post_init__(self) -> None:
        self.patterns = [_coerce_element(p) for p in self.patterns]


def _coerce_element(p: Any) -> Any:
    """Pass typed elements through; coerce a bare dict to a :class:`Pattern`."""
    if isinstance(p, (Pattern, Exists, Accumulate)):
        return p
    return Pattern(**p)


@dataclass(frozen=True)
class Activation:
    """A complete, fired multi-fact match.

    Attributes:
        rule_id: The matched rule's id.
        rule_name: The matched rule's name.
        facts: The bound fact handle ids, in pattern order (the match's identity).
        bindings: ``var -> fact fields`` for each bound pattern, for action use.
        aggregates: ``var -> aggregate value`` for each :class:`Accumulate`
            element (B-γ). Empty for pure join rules.
    """

    rule_id: int
    rule_name: str
    facts: tuple[int, ...]
    bindings: dict[str, dict[str, Any]] = dc_field(default_factory=dict, hash=False)
    aggregates: dict[str, Any] = dc_field(default_factory=dict, hash=False)


__all__ = [
    "AGG_FUNCTIONS",
    "TEMPORAL_RELATIONS",
    "Accumulate",
    "Activation",
    "AlphaConstraint",
    "CrossFactRule",
    "Exists",
    "FactHandle",
    "JoinConstraint",
    "Pattern",
    "TemporalConstraint",
    "normalize_op",
]
