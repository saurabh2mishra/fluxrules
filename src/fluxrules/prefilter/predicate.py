"""Predicate extraction: turn rule ``condition_dsl`` into sound pre-filters.

A rule fires only if *all* required leaf conditions are satisfied. The engine's
operator semantics (see ``fluxrules.engine.operators.evaluate_operator``) give us
the soundness lever we need: **a leaf whose field is absent evaluates to False**,
and **a leaf with value None evaluates to False** (unless ``== None``). So a rule
can only fire when its mandatory fields are present and within range.

This module derives, per rule, a *necessary condition* for firing - a conjunction
of per-field constraints that MUST hold. We then union these across all rules to
get a :class:`PredicateSet` describing "any fact a rule could care about". The
SQL store turns that into indexed ``WHERE`` clauses.

Soundness rules
---------------
- ``AND`` node: a rule needs *all* children, so we may safely keep any subset of
  child constraints as necessary conditions (we keep the leaf constraints we can
  translate; unknown children are simply dropped - dropping a necessary clause
  only makes the filter *looser*, never unsound).
- ``OR`` node: a rule needs *at least one* child. We can only push a field
  constraint if it is implied by *every* branch (the field is constrained in all
  branches). Otherwise the field is unconstrained for this rule.
- ``NOT`` node / unsupported ops / cross-field / custom predicates: treated as
  "unconstrained" - the rule contributes no filter and is treated as
  *always-candidate* (we never drop a fact on its behalf).

The guiding invariant: **when in doubt, pass the fact through.** Looser filters
cost extra engine work; they never cause a missed match.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable
from dataclasses import dataclass
from dataclasses import field as dataclass_field
from typing import Any

logger = logging.getLogger(__name__)

# Operators we can translate into SQL range/membership constraints.
_RANGE_OPS = {">", ">=", "<", "<="}
_EQ_OPS = {"==", "!="}
_MEMBER_OPS = {"in"}
TRANSLATABLE_OPS = _RANGE_OPS | _EQ_OPS | _MEMBER_OPS

# A rule contributes a constraint only for "positive" operators - those that
# require the field to be present with a constraining value. ``!=`` and
# ``not_in`` are NOT constraining (almost any value passes), so they yield no
# filter (field stays unconstrained), which is sound.
_CONSTRAINING_OPS = _RANGE_OPS | {"=="} | _MEMBER_OPS


@dataclass
class LeafPredicate:
    """A single translatable constraint on one field, e.g. ``field_3 > 500``."""

    field: str
    op: str
    value: Any


@dataclass
class FieldConstraint:
    """The union (across rules) of constraints on a single field.

    Because rules are OR-ed together at the *set* level (a fact is a candidate if
    *any* rule could match it), per-field constraints from different rules are
    UNION-ed. We track the loosest envelope that still bounds every contributing
    rule:

    - ``lo`` / ``hi``: numeric envelope; ``None`` means unbounded on that side.
    - ``lo_inclusive`` / ``hi_inclusive``: whether the bound is inclusive.
    - ``eq_values``: set of equality / membership values.
    - ``unconstrained``: if True, at least one rule needs this field with no
      translatable bound, so the field must not be used to exclude facts.
    """

    field: str
    lo: float | None = None
    lo_inclusive: bool = True
    hi: float | None = None
    hi_inclusive: bool = True
    eq_values: set[Any] = dataclass_field(default_factory=set)
    has_range: bool = False
    has_eq: bool = False
    unconstrained: bool = False

    def widen_range(self, lo: float | None, lo_incl: bool, hi: float | None, hi_incl: bool) -> None:
        """Union a numeric range into the envelope (loosen bounds)."""
        self.has_range = True
        if lo is None:
            self.lo, self.lo_inclusive = None, True
        elif self.lo is not None:
            if lo < self.lo or (lo == self.lo and lo_incl):
                self.lo, self.lo_inclusive = lo, lo_incl
        # else: self.lo already None (unbounded) -> stays unbounded
        if hi is None:
            self.hi, self.hi_inclusive = None, True
        elif self.hi is not None:
            if hi > self.hi or (hi == self.hi and hi_incl):
                self.hi, self.hi_inclusive = hi, hi_incl

    def add_eq(self, value: Any) -> None:
        try:
            self.eq_values.add(value)
        except TypeError:
            # An unhashable equality value (list/dict) cannot be indexed. Keep
            # the field unconstrained so the rule stays a candidate and is
            # confirmed by full evaluation - looser filter, never unsound.
            self.mark_unconstrained()
            return
        self.has_eq = True

    def mark_unconstrained(self) -> None:
        self.unconstrained = True


@dataclass
class RuleClause:
    """The necessary per-field constraints extracted from a single rule.

    Maps field name -> :class:`LeafPredicate` that MUST hold for the rule to fire.
    An empty mapping means "no usable filter" (rule is always a candidate).
    """

    rule_id: int
    must: dict[str, LeafPredicate] = dataclass_field(default_factory=dict)
    always_candidate: bool = False


@dataclass
class PredicateSet:
    """Union of all rule constraints - the input to the SQL store.

    Attributes:
        fields: every field referenced by any rule (defines the table schema).
        constraints: field -> :class:`FieldConstraint` envelope used for WHERE.
        always_candidate_rules: rules with no usable filter; if non-empty for a
            field set, that field cannot exclude facts.
        has_unfilterable_rule: True if at least one rule cannot be filtered at all
            (e.g. NOT / custom predicate). When True the store must return all
            facts (the pre-filter degrades to a pass-through but stays sound).
    """

    fields: set[str] = dataclass_field(default_factory=set)
    constraints: dict[str, FieldConstraint] = dataclass_field(default_factory=dict)
    always_candidate_rules: set[int] = dataclass_field(default_factory=set)
    has_unfilterable_rule: bool = False
    # Per-rule necessary clauses that CAN be pushed to SQL (non-empty ``must``).
    # The store ORs these together (DNF) to select candidates precisely.
    filterable_clauses: list[RuleClause] = dataclass_field(default_factory=list)

    def constraint(self, field_name: str) -> FieldConstraint:
        return self.constraints.setdefault(field_name, FieldConstraint(field=field_name))


class PredicateExtractor:
    """Extract a sound :class:`PredicateSet` from a collection of rules."""

    def from_rules(self, rules: Iterable[Any]) -> PredicateSet:
        ps = PredicateSet()
        for rule in rules:
            if getattr(rule, "enabled", True) is False:
                continue
            clause = self._extract_rule(rule)
            self._merge_clause(ps, clause)
        return ps

    # per-rule extraction

    def _extract_rule(self, rule: Any) -> RuleClause:
        clause = RuleClause(rule_id=getattr(rule, "id", 0))
        dsl = getattr(rule, "condition_dsl", None)
        if not isinstance(dsl, dict):
            clause.always_candidate = True
            return clause
        must = self._necessary(dsl)
        if must is None:
            # Rule contains a construct we can't bound -> always a candidate.
            clause.always_candidate = True
        else:
            clause.must = must
        return clause

    def _necessary(self, dsl: dict[str, Any]) -> dict[str, LeafPredicate] | None:
        """Return field->predicate that MUST hold, or ``None`` if unbounded.

        ``None`` signals "cannot derive a sound filter for this subtree" and must
        propagate up as always-candidate for safety.
        """
        ctype = dsl.get("type")

        if ctype == "condition":
            f, op, val = dsl.get("field"), dsl.get("op"), dsl.get("value")
            if not f or op not in _CONSTRAINING_OPS:
                # Non-constraining (e.g. !=, not_in, custom) -> no filter, but the
                # rest of an AND may still constrain. Empty dict = "nothing from
                # this leaf" rather than None (None would over-loosen the parent).
                return {}
            if op in _RANGE_OPS and not _is_number(val):
                return {}
            return {f: LeafPredicate(field=f, op=op, value=val)}

        # ``composite``/``group`` carry an explicit ``logic`` (AND/OR). Route by
        # it so an OR composite is NOT mistakenly treated as a conjunction (which
        # would be UNSOUND - it would drop facts matching only one branch).
        if ctype in ("composite", "group"):
            logic = str(dsl.get("logic", "and")).lower()
            ctype = "or" if logic == "or" else "and"

        if ctype == "and":
            children = dsl.get("conditions") or dsl.get("children") or []
            merged: dict[str, LeafPredicate] = {}
            for child in children:
                if not isinstance(child, dict):
                    continue
                sub = self._necessary(child)
                if sub is None:
                    # One AND branch is unbounded, but the OTHER branches are
                    # still necessary -> keep what we have (sound: subset of a
                    # conjunction is still necessary). Skip the unbounded child.
                    continue
                for fld, pred in sub.items():
                    # On field collision within an AND, keep the first; the store
                    # envelope unions anyway. (Tightening is an optional B.2 win.)
                    merged.setdefault(fld, pred)
            return merged

        if ctype == "or":
            children = dsl.get("conditions") or dsl.get("children") or []
            if not children:
                return {}
            branch_maps: list[dict[str, LeafPredicate]] = []
            for child in children:
                if not isinstance(child, dict):
                    return None  # opaque branch -> OR could match anything
                sub = self._necessary(child)
                if sub is None or not sub:
                    # A branch with no usable constraint means the OR can be
                    # satisfied without constraining any field -> unbounded.
                    return None
                branch_maps.append(sub)
            # A field is necessary only if constrained in EVERY branch.
            common = set(branch_maps[0])
            for m in branch_maps[1:]:
                common &= set(m)
            if not common:
                return None
            # For each common field, the OR allows any branch's value -> we cannot
            # safely tighten to one predicate, so treat as present-but-unbounded by
            # emitting a sentinel "exists" predicate (field must be present).
            return {f: LeafPredicate(field=f, op="__exists__", value=None) for f in common}

        # not / exists / accumulate / unknown -> cannot bound soundly.
        return None

    # merge into the global PredicateSet

    def _merge_clause(self, ps: PredicateSet, clause: RuleClause) -> None:
        if clause.always_candidate:
            ps.always_candidate_rules.add(clause.rule_id)
            ps.has_unfilterable_rule = True
            return
        if not clause.must:
            # Rule referenced only non-constraining ops -> always candidate.
            ps.always_candidate_rules.add(clause.rule_id)
            ps.has_unfilterable_rule = True
            return
        for fld, pred in clause.must.items():
            ps.fields.add(fld)
            fc = ps.constraint(fld)
            self._apply_predicate(fc, pred)
        ps.filterable_clauses.append(clause)

    @staticmethod
    def _apply_predicate(fc: FieldConstraint, pred: LeafPredicate) -> None:
        op, val = pred.op, pred.value
        if op == "__exists__":
            # Field must be present but value is unbounded across an OR.
            fc.mark_unconstrained()
            return
        if op in _EQ_OPS:  # only "==" reaches here (constraining)
            fc.add_eq(val)
            return
        if op in _MEMBER_OPS:  # "in"
            if isinstance(val, (list, tuple, set, frozenset)):
                for v in val:
                    fc.add_eq(v)
            else:
                fc.mark_unconstrained()
            return
        if op == ">":
            fc.widen_range(val, False, None, True)
        elif op == ">=":
            fc.widen_range(val, True, None, True)
        elif op == "<":
            fc.widen_range(None, True, val, False)
        elif op == "<=":
            fc.widen_range(None, True, val, True)


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)
