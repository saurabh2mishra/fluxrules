"""Cross-fact join engine (stages B-α + B-β + B-γ + B-δ).

What this is
------------
A **separate** engine - *not* a modification of the single-fact ``PhreakEngine`` -
that holds many typed facts in working memory and matches **tuples of facts**
across patterns. It implements the foundational stages of the Track B design
note:

- **B-α - fact lifecycle + truth maintenance.** ``insert`` / ``update`` /
  ``retract`` mutate working memory and return the **delta** of activations
  (matches gained and lost). Crucially, a ``retract`` *un-fires* every activation
  that depended on the removed fact - the property a stateless single-fact engine
  never needs and cannot provide.
- **B-β - indexed equality joins + token propagation.** Joins between patterns
  are evaluated by extending partial-match tuples ("tokens") pattern by pattern;
  equality joins probe a **hash index** (O(matching facts)) instead of scanning
  every fact of the type (O(L×R)).

B-γ adds, on top of those:

- **Collection aggregates** (:class:`~fluxrules.engine.cross_fact.models.Accumulate`):
  ``count`` / ``sum`` / ``avg`` / ``min`` / ``max`` / ``collect`` over the facts
  of a type that satisfy alpha + join filters, with an optional ``having``
  threshold (e.g. *"sum of this customer's orders ≥ 10000"*).
- **Working-memory quantifiers** (:class:`~fluxrules.engine.cross_fact.models.Exists`):
  ``exists`` / ``not`` over working memory, gating a match on the presence or
  **absence** of a correlated fact (e.g. *"an order with no matching shipment"*).

Both participate in the same incremental truth maintenance: because a rule is
recomputed whenever a fact of a referenced type changes, retracting the last
member of an aggregate or emptying an ``exists`` correctly updates (or un-fires)
the dependent activations.

B-δ adds, on top of those:

- **Temporal windows** (:class:`~fluxrules.engine.cross_fact.models.TemporalConstraint`):
  Allen-style ``within`` / ``after`` / ``before`` relations between a fact's
  event-time and an earlier-bound fact's, bounded by a ``window`` (sliding by
  event-time). They gate a join exactly like a join constraint, but over time.
- **An event clock + window expiration.** The engine clock advances to the
  newest timestamp seen (event-time, not wall-clock). A fact older than the
  widest window that could still match it can never again satisfy a temporal
  constraint, so it is **auto-retracted** - bounding memory under an unbounded
  stream (the memory-safety crux of design note B.5), reusing the same truth
  maintenance to un-fire any activations the expired fact supported.

Scope (intentionally bounded for this stage)
--------------------------------------------
Conjunctive multi-pattern joins with alpha (field vs. literal), join (field vs.
earlier-bound field), and **temporal** (event-time window) constraints,
collection aggregates, and ``exists`` / ``not`` quantifiers - all with correct
incremental truth maintenance and event-time window expiration. The remaining
``during`` / ``overlaps`` / ``meets`` Allen relations and beta-network metrics
(B-ε) are out of scope here; see
``.research/PHREAK_P3_PLAN_CROSS_FACT_NETWORK.md``.

Determinism
-----------
``insert``/``update``/``retract`` return deltas sorted by ``(rule_id, facts)`` so
results are reproducible regardless of dict iteration order (design note B.6).
"""

from __future__ import annotations

import logging
from typing import Any, TypeGuard

from fluxrules.engine.configuration import get_config
from fluxrules.engine.cross_fact.models import (
    Accumulate,
    Activation,
    CrossFactRule,
    Exists,
    FactHandle,
    Pattern,
)
from fluxrules.engine.cross_fact.working_memory import CrossFactWorkingMemory
from fluxrules.engine.operators import evaluate_operator

logger = logging.getLogger(__name__)


def _is_number(value: Any) -> TypeGuard[float]:
    """True for a real numeric timestamp (``int``/``float`` but **not** ``bool``).

    ``bool`` is an ``int`` subclass in Python; excluding it stops ``True``/``False``
    from being treated as event-times ``1``/``0`` on the temporal timeline.
    """
    return isinstance(value, (int, float)) and not isinstance(value, bool)


class CrossFactDelta:
    """The change in activations produced by one working-memory mutation.

    Attributes:
        added: activations that became true (newly satisfied matches).
        removed: activations that became false (matches invalidated, e.g. by a
            retract or an update that broke a join).
        handle: the fact handle that was inserted / updated / retracted. Exposed
            so callers can keep a stable id to ``update``/``retract`` later
            without scanning working memory. ``None`` only when a ``retract``
            targeted an unknown id.
    """

    __slots__ = ("added", "handle", "removed")

    def __init__(
        self,
        added: list[Activation],
        removed: list[Activation],
        handle: FactHandle | None = None,
    ) -> None:
        self.added = added
        self.removed = removed
        self.handle = handle

    def __bool__(self) -> bool:
        return bool(self.added or self.removed)

    def __repr__(self) -> str:  # pragma: no cover - cosmetic
        return f"CrossFactDelta(added={len(self.added)}, removed={len(self.removed)})"


class CrossFactEngine:
    """Multi-fact join engine with incremental truth maintenance.

    Example::

        engine = CrossFactEngine()
        engine.load_rules([
            CrossFactRule(
                id=1,
                name="big-order-gold-customer",
                patterns=[
                    Pattern("o", "Order", constraints=[("amount", ">", 1000)]),
                    Pattern("c", "Customer",
                            constraints=[("tier", "==", "gold")],
                            joins=[("id", "==", "o", "customer_id")]),
                ],
            )
        ])
        engine.insert("Customer", {"id": 7, "tier": "gold"})
        delta = engine.insert("Order", {"customer_id": 7, "amount": 5000})
        # delta.added -> the firing tuple (Order, Customer)
    """

    def __init__(self, *, time_field: str = "ts") -> None:
        self.wm = CrossFactWorkingMemory()
        self._rules: dict[int, CrossFactRule] = {}
        # rule_id -> { fact_tuple -> Activation } currently believed true.
        self._activations: dict[int, dict[tuple[int, ...], Activation]] = {}
        # fact_type -> {rule_id, ...} that reference it (recompute trigger set).
        self._rules_by_type: dict[str, set[int]] = {}
        self._cfg = get_config()
        # Temporal (B-δ). ``time_field`` is the per-fact event-time attribute;
        # the engine clock advances to the max timestamp ever seen (event-time,
        # not wall-clock). ``_max_window_by_type`` is the longest window any rule
        # applies to a given fact type, used to expire facts that can never match
        # again. Empty until a rule declares a temporal constraint, so non-temporal
        # rule sets pay nothing.
        self._time_field = time_field
        self._clock: float | None = None
        self._max_window_by_type: dict[str, float] = {}

    # --- rule management -----------------------------------------------------

    def load_rules(self, rules: list[CrossFactRule]) -> None:
        """Replace the rule set and recompute all activations from scratch."""
        self._rules = {r.id: r for r in rules}
        self._rules_by_type = {}
        self._max_window_by_type = {}
        for rule in rules:
            # ``var -> fact_type`` for this rule's bound patterns, built in join
            # order so a temporal constraint can resolve the type of the earlier
            # var it references (only Patterns bind a fact var).
            var_types: dict[str, str] = {}
            for element in rule.patterns:
                # Every element - Pattern, Exists, Accumulate - exposes
                # ``fact_type``; a change to any referenced type must re-trigger
                # this rule.
                self._rules_by_type.setdefault(element.fact_type, set()).add(rule.id)
                # A temporal window bounds memory on **both** sides of the
                # relation: this element's own facts *and* the earlier fact it is
                # timed against can each be expired once older than ``window``
                # behind the clock. Registering both keeps an unbounded stream
                # from accreting the upstream type forever (design note B.5).
                for tc in getattr(element, "temporal", ()):
                    self._note_window(element.fact_type, tc.window)
                    other_type = var_types.get(tc.other_var)
                    if other_type is not None:
                        self._note_window(other_type, tc.window)
                if isinstance(element, Pattern):
                    var_types[element.var] = element.fact_type
        self._activations = {r.id: {} for r in rules}
        for rule in rules:
            self._recompute_rule(rule)

    def _note_window(self, fact_type: str, window: float) -> None:
        """Record the widest temporal window applied to a fact type (B-δ)."""
        cur = self._max_window_by_type.get(fact_type, 0.0)
        self._max_window_by_type[fact_type] = max(cur, window)

    @property
    def rules(self) -> dict[int, CrossFactRule]:
        return self._rules

    # --- fact lifecycle (B-α) ------------------------------------------------

    def insert(self, fact_type: str, fields: dict[str, Any]) -> CrossFactDelta:
        """Insert a fact; return the activation delta (with the new handle).

        If the fact carries the event-time field, the engine clock advances to
        the newest timestamp seen, then **expired** facts (older than any window
        that could still match them) are auto-retracted *before* reconciling - so
        a single diff pass reports the net effect of the insert **and** every
        expiry it triggered. This bounds memory under an unbounded stream (B-δ).
        """
        handle = self.wm.insert(fact_type, fields)
        self._advance_clock(fields)
        # Expire stale facts first, then reconcile every rule touching either the
        # inserted type or an expired one in one diff - no double-reporting.
        affected = {fact_type} | self._expire_facts()
        return self._reconcile(affected, handle)

    def update(self, handle_id: int, fields: dict[str, Any]) -> CrossFactDelta:
        """Update a fact in place (identity preserved); return the delta."""
        handle = self.wm.get(handle_id)
        if handle is None:
            raise KeyError(f"unknown fact handle: {handle_id}")
        fact_type = handle.fact_type
        handle = self.wm.update(handle_id, fields)
        self._advance_clock(fields)
        affected = {fact_type} | self._expire_facts()
        return self._reconcile(affected, handle)

    def retract(self, handle_id: int) -> CrossFactDelta:
        """Retract a fact; return the delta (includes un-fired activations)."""
        handle = self.wm.get(handle_id)
        if handle is None:
            return CrossFactDelta(added=[], removed=[], handle=None)
        fact_type = handle.fact_type
        self.wm.retract(handle_id)
        return self._reconcile({fact_type}, handle)

    def clear(self) -> None:
        self.wm.clear()
        self._activations = {rid: {} for rid in self._rules}
        self._clock = None

    # --- temporal clock + window expiration (B-δ) ---------------------------

    @property
    def clock(self) -> float | None:
        """Current event-time of the engine (max timestamp seen), or ``None``."""
        return self._clock

    def _advance_clock(self, fields: dict[str, Any]) -> None:
        """Advance the event clock to the newest timestamp observed.

        Event-time (driven by the data), not wall-clock - so replays and tests
        are deterministic and out-of-order arrivals never rewind the clock.
        """
        ts = fields.get(self._time_field)
        if _is_number(ts):
            self._clock = ts if self._clock is None else max(self._clock, ts)

    def _expire_facts(self) -> set[str]:
        """Retract facts too old to satisfy any window; return the types touched.

        A fact of a type with max window ``W`` can never again satisfy a temporal
        constraint once its timestamp is older than ``clock - W``. Removing it
        bounds working memory under a continuous stream - the memory-safety crux
        of B-δ (design note B.5). The returned types are folded into the caller's
        reconcile pass so a single diff un-fires every activation the expired
        facts supported (e.g. an ``Exists``/``not`` flip), with no double-report.
        """
        if self._clock is None or not self._max_window_by_type:
            return set()
        doomed: list[int] = []
        for fact_type, window in self._max_window_by_type.items():
            horizon = self._clock - window
            for handle in self.wm.by_type(fact_type):
                ts = handle.fields.get(self._time_field)
                if _is_number(ts) and ts < horizon:
                    doomed.append(handle.id)
        affected: set[str] = set()
        for hid in doomed:
            retracted = self.wm.retract(hid)
            if retracted is not None:
                affected.add(retracted.fact_type)
        return affected

    # --- introspection -------------------------------------------------------

    def activations(self) -> list[Activation]:
        """All currently-true activations, deterministically ordered."""
        out: list[Activation] = []
        for rule_acts in self._activations.values():
            out.extend(rule_acts.values())
        out.sort(key=lambda a: (a.rule_id, a.facts))
        return out

    def get_stats(self) -> dict[str, Any]:
        return {
            "engine_type": type(self).__name__,
            "rules_loaded": len(self._rules),
            "facts_in_memory": len(self.wm),
            "active_activations": sum(len(a) for a in self._activations.values()),
        }

    # --- truth maintenance core ---------------------------------------------

    def _reconcile(self, fact_types: set[str], handle: FactHandle | None = None) -> CrossFactDelta:
        """Recompute rules touching ``fact_types`` and diff against prior state.

        Recomputing the full match set for the affected rules and diffing is the
        simplest *correct* truth-maintenance strategy: it guarantees retract and
        join-breaking updates remove activations, which is the entire point of
        B-α. ``fact_types`` may name more than one type - e.g. an insert plus the
        types of any facts B-δ expiration retracted - so a single diff pass
        reports the net effect with no double-counting. The indexed join (B-β)
        keeps each recompute cheap; finer-grained incrementality is a later
        optimization (design note B.2).
        """
        added: list[Activation] = []
        removed: list[Activation] = []
        affected_rules: set[int] = set()
        for fact_type in fact_types:
            affected_rules |= self._rules_by_type.get(fact_type, set())
        for rule_id in affected_rules:
            rule = self._rules[rule_id]
            old = self._activations[rule_id]
            new = self._match_rule(rule)
            for key, act in new.items():
                if key not in old:
                    added.append(act)
            for key, act in old.items():
                if key not in new:
                    removed.append(act)
            self._activations[rule_id] = new
        added.sort(key=lambda a: (a.rule_id, a.facts))
        removed.sort(key=lambda a: (a.rule_id, a.facts))
        return CrossFactDelta(added=added, removed=removed, handle=handle)

    def _recompute_rule(self, rule: CrossFactRule) -> None:
        self._activations[rule.id] = self._match_rule(rule)

    # --- join evaluation (B-β) + quantifiers/aggregates (B-γ) ---------------

    def _match_rule(self, rule: CrossFactRule) -> dict[tuple[int, ...], Activation]:
        """Return all complete matches for a rule as ``{fact_tuple: Activation}``.

        A *token* is a partial match carried through the rule body element by
        element:

        - :class:`Pattern` - **binds** a fact, extending the token's fact tuple
          (B-β join via the hash index).
        - :class:`Exists` - a **quantifier**: keeps or drops the token based on
          the presence/absence of a matching fact, binding nothing (B-γ).
        - :class:`Accumulate` - reduces a **collection** of facts to a value,
          attaches it to the token, and applies an optional ``having`` threshold
          (B-γ).
        """
        # Each token: (fact-id tuple, {var: FactHandle}, {agg_var: value}).
        tokens: list[tuple[tuple[int, ...], dict[str, Any], dict[str, Any]]] = [((), {}, {})]
        for element in rule.patterns:
            if isinstance(element, Pattern):
                tokens = self._extend(tokens, element)
            elif isinstance(element, Exists):
                tokens = self._filter_exists(tokens, element)
            elif isinstance(element, Accumulate):
                tokens = self._apply_accumulate(tokens, element)
            else:  # pragma: no cover - guarded by model coercion
                raise TypeError(f"unknown rule element: {type(element).__name__}")
            if not tokens:
                return {}

        results: dict[tuple[int, ...], Activation] = {}
        for fact_ids, binding, aggregates in tokens:
            results[fact_ids] = Activation(
                rule_id=rule.id,
                rule_name=rule.name,
                facts=fact_ids,
                bindings={var: h.fields for var, h in binding.items()},
                aggregates=dict(aggregates),
            )
        return results

    def _extend(
        self,
        tokens: list[tuple[tuple[int, ...], dict[str, Any], dict[str, Any]]],
        pattern: Pattern,
    ) -> list[tuple[tuple[int, ...], dict[str, Any], dict[str, Any]]]:
        extended: list[tuple[tuple[int, ...], dict[str, Any], dict[str, Any]]] = []
        for fact_ids, binding, aggregates in tokens:
            for candidate in self._candidates(pattern, binding):
                if candidate.id in fact_ids:
                    continue  # a fact may not bind two patterns in one match
                if not self._alphas_hold(pattern, candidate):
                    continue
                if not self._joins_hold(pattern, candidate, binding):
                    continue
                if not self._temporals_hold(pattern, candidate, binding):
                    continue
                new_binding = dict(binding)
                new_binding[pattern.var] = candidate
                extended.append((fact_ids + (candidate.id,), new_binding, aggregates))
        return extended

    def _filter_exists(
        self,
        tokens: list[tuple[tuple[int, ...], dict[str, Any], dict[str, Any]]],
        quant: Exists,
    ) -> list[tuple[tuple[int, ...], dict[str, Any], dict[str, Any]]]:
        """Keep tokens per an ``exists`` / ``not`` quantifier (binds nothing)."""
        survivors: list[tuple[tuple[int, ...], dict[str, Any], dict[str, Any]]] = []
        for token in tokens:
            _fact_ids, binding, _aggs = token
            found = any(
                fact.id not in _fact_ids
                and self._alphas_hold(quant, fact)
                and self._joins_hold(quant, fact, binding)
                and self._temporals_hold(quant, fact, binding)
                for fact in self._candidates(quant, binding)
            )
            if found != quant.negated:  # exists->found True; not->found False
                survivors.append(token)
        return survivors

    def _apply_accumulate(
        self,
        tokens: list[tuple[tuple[int, ...], dict[str, Any], dict[str, Any]]],
        acc: Accumulate,
    ) -> list[tuple[tuple[int, ...], dict[str, Any], dict[str, Any]]]:
        """Reduce a collection to a value, bind it, and apply ``having`` (B-γ)."""
        survivors: list[tuple[tuple[int, ...], dict[str, Any], dict[str, Any]]] = []
        for fact_ids, binding, aggregates in tokens:
            matched = [
                fact
                for fact in self._candidates(acc, binding)
                if fact.id not in fact_ids
                and self._alphas_hold(acc, fact)
                and self._joins_hold(acc, fact, binding)
                and self._temporals_hold(acc, fact, binding)
            ]
            value = self._aggregate(acc, matched)
            if acc.having is not None:
                op, threshold = acc.having
                if not self._op(op, value, threshold, present=True):
                    continue
            new_aggs = dict(aggregates)
            new_aggs[acc.var] = value
            survivors.append((fact_ids, binding, new_aggs))
        return survivors

    @staticmethod
    def _aggregate(acc: Accumulate, facts: list[Any]) -> Any:
        """Reduce ``facts`` to a scalar (or list for ``collect``).

        ``min``/``max``/``avg`` over an **empty** collection return ``None`` (no
        defined value); ``sum`` is ``0``, ``count`` is ``0``, ``collect`` is
        ``[]`` - the conventional, defensible defaults.
        """
        fn = acc.function
        if fn == "count":
            return len(facts)
        values = [f.fields[acc.field] for f in facts if acc.field in f.fields]
        if fn == "collect":
            return values
        if fn == "sum":
            return sum(values)
        if not values:
            return None
        if fn == "avg":
            return sum(values) / len(values)
        if fn == "min":
            return min(values)
        if fn == "max":
            return max(values)
        raise ValueError(f"unhandled aggregate function {fn!r}")  # pragma: no cover

    def _candidates(self, pattern: Any, binding: dict[str, Any]) -> list[Any]:
        """Candidate facts for an element, using the hash index when possible.

        Works for :class:`Pattern`, :class:`Exists`, and :class:`Accumulate` -
        all expose ``fact_type`` and ``joins``. If the element has an equality
        join against an already-bound variable, we probe the index by the bound
        value (B-β: O(matching facts)). Otherwise we scan the element's type.
        """
        for join in pattern.joins:
            if join.is_equality and join.other_var in binding:
                other = binding[join.other_var]
                if join.other_field not in other.fields:
                    return []
                probe = other.fields[join.other_field]
                return self.wm.by_equality(pattern.fact_type, join.this_field, probe)
        return self.wm.by_type(pattern.fact_type)

    def _alphas_hold(self, pattern: Any, fact: Any) -> bool:
        for c in pattern.constraints:
            present = c.field in fact.fields
            if not self._op(c.op, fact.fields.get(c.field), c.value, present):
                return False
        return True

    def _joins_hold(self, pattern: Any, fact: Any, binding: dict[str, Any]) -> bool:
        for join in pattern.joins:
            other = binding.get(join.other_var)
            if other is None:
                # Join references a pattern not yet bound - invalid rule shape.
                logger.warning(
                    "beta join references unbound var '%s'; treating as no-match",
                    join.other_var,
                )
                return False
            present = join.this_field in fact.fields and join.other_field in other.fields
            left = fact.fields.get(join.this_field)
            right = other.fields.get(join.other_field)
            if not self._op(join.op, left, right, present):
                return False
        return True

    def _temporals_hold(self, element: Any, fact: Any, binding: dict[str, Any]) -> bool:
        """Whether ``fact`` satisfies every temporal window of ``element`` (B-δ).

        Each :class:`TemporalConstraint` relates this fact's event-time to an
        earlier-bound fact's within a ``window``, using Allen-style ``within`` /
        ``after`` / ``before`` semantics. A missing or non-numeric timestamp on
        either side fails the constraint (we cannot place the event on the
        timeline, so it cannot be inside any window).
        """
        for tc in getattr(element, "temporal", ()):  # empty for non-temporal rules
            other = binding.get(tc.other_var)
            if other is None:
                logger.warning(
                    "beta temporal references unbound var '%s'; treating as no-match",
                    tc.other_var,
                )
                return False
            this_ts = fact.fields.get(tc.this_field or self._time_field)
            other_ts = other.fields.get(tc.other_field or self._time_field)
            if not _is_number(this_ts) or not _is_number(other_ts):
                return False
            delta = this_ts - other_ts
            if tc.relation == "within":
                # Order-independent: the two events are within `window`.
                if abs(delta) > tc.window:
                    return False
            elif tc.relation == "after":
                # This happened after `other`, no more than `window` later.
                if delta < 0 or delta > tc.window:
                    return False
            elif tc.relation == "before":
                # This happened before `other`, no more than `window` earlier.
                if delta > 0 or -delta > tc.window:
                    return False
        return True

    def _op(self, op: str, left: Any, right: Any, present: bool) -> bool:
        """Evaluate one comparison, sharing the engine-wide operator semantics."""
        return evaluate_operator(
            op,
            left,
            right,
            field_present=present,
            strict_null_handling=self._cfg.strict_null_handling,
            strict_type_comparison=self._cfg.strict_type_comparison,
            boolean_string_coercion=self._cfg.boolean_string_coercion,
            emit_metrics=False,
        )


__all__ = ["CrossFactDelta", "CrossFactEngine"]
