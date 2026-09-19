"""In-memory predicate index - a streaming alpha-screen in front of the engine.

Why this exists
---------------
A rule engine's facts are **transient events**: they arrive as a stream (or in
bulk batches), are evaluated against rules held in memory, and are discarded.
They are *not* a queryable dataset, so there is nothing to load into a database
and index.

The right pre-screen is therefore an **in-memory alpha index** built once from
the rule set: each distinct leaf predicate ``(field, op, value)`` becomes an
"alpha node". For a streaming fact we evaluate each *distinct* predicate at most
once and ask the cheap question:

    "Could this fact satisfy the necessary conditions of *any* rule?"

If not, the fact never reaches the CPU-bound ``engine.evaluate()``. This is the
classic PHREAK alpha network, scoped to a sound pre-screen.

Soundness contract (identical to the old DB store, minus the DB)
----------------------------------------------------------------
For any fact ``f`` and rule set ``R``: if ``engine.evaluate(f)`` fires any rule,
then ``index.matches(f)`` is True. False positives (extra candidates) are allowed
and removed by exact engine evaluation; false negatives are never allowed.

The necessary-condition extraction is reused verbatim from
:class:`fluxrules.prefilter.predicate.PredicateExtractor`, which already encodes
the engine's operator semantics (absent field -> False, ``OR`` only constrains a
field present in every branch, unsupported ops -> always-candidate).
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Iterable, Iterator
from dataclasses import dataclass, field
from typing import Any

from fluxrules.prefilter.predicate import (
    LeafPredicate,
    PredicateExtractor,
    PredicateSet,
)

logger = logging.getLogger(__name__)

# Sentinel used when a field is absent from a fact. Distinct from None so that a
# rule testing ``== None`` is handled correctly (absent != explicit None).
_MISSING = object()


def _make_test(op: str, value: Any) -> Callable[[Any], bool]:
    """Compile a leaf predicate into a fast unary test over a fact's field value.

    The callable receives the field's value (or ``_MISSING`` when absent) and
    returns whether the leaf is satisfied. Mirrors the engine's operator
    semantics: an absent or ``None`` value fails every constraining operator.
    """
    if op == "__exists__":
        return lambda v: v is not _MISSING and v is not None
    if op == "==":
        return lambda v: v is not _MISSING and v == value
    if op == "in":
        members = set(value) if isinstance(value, (list, tuple, set, frozenset)) else {value}
        return lambda v: v is not _MISSING and v in members
    if op == ">":
        return lambda v: v is not _MISSING and v is not None and v > value
    if op == ">=":
        return lambda v: v is not _MISSING and v is not None and v >= value
    if op == "<":
        return lambda v: v is not _MISSING and v is not None and v < value
    if op == "<=":
        return lambda v: v is not _MISSING and v is not None and v <= value
    # Should never reach here: extractor only emits constraining ops.
    return lambda v: True


@dataclass(frozen=True)
class _AlphaNode:
    """A single distinct leaf predicate evaluated at most once per fact."""

    field: str
    op: str
    value_key: Any  # hashable form of the value, for dedup
    test: Callable[[Any], bool]


@dataclass
class PredicateIndex:
    """Streaming alpha-screen: "could this fact match any rule?".

    Build once from a rule set, then call :meth:`matches` per streaming fact or
    :meth:`filter` over a batch/stream. No I/O, no database, no full
    materialization - facts flow through one at a time.

    Two granularities are exposed:

    - :meth:`matches` - *fact-level*: "could ANY rule fire?" Cheapest gate; used
      to drop facts before the engine is touched at all.
    - :meth:`candidate_rule_ids` - *rule-level*: the set of rule ids whose
      necessary conditions all pass (the alpha survivors), **plus** every
      unfilterable rule (which must always be considered). This is the alpha
      layer that narrows the engine's per-fact rule set even when some rules are
      unfilterable.

    Clauses are **deduplicated by signature**: rules that share identical
    necessary conditions (very common - e.g. 1000 rules all needing
    ``amount > 100``) collapse to a single signature mapped to the set of rule
    ids. This keeps the per-fact cost ``O(distinct signatures)``, not
    ``O(rules)``, and lets :meth:`candidate_rule_ids` short-circuit to "no
    pruning" cheaply when every signature passes.

    Attributes:
        pass_through: when True, at least one rule cannot be soundly bounded
            (e.g. NOT / custom predicate / cross-field). :meth:`matches` then
            always returns True (every fact is a candidate). :meth:`candidate_rule_ids`
            still prunes the *filterable* rules and unions the unfilterable ones.
    """

    _nodes: list[_AlphaNode] = field(default_factory=list)
    # Distinct clause signatures: each is a sorted tuple of alpha-node ids that
    # must ALL pass. Parallel list ``_signature_rules`` holds the rule ids that
    # share that signature.
    _signatures: list[tuple[int, ...]] = field(default_factory=list)
    _signature_rules: list[frozenset[int]] = field(default_factory=list)
    # field -> ids of alpha nodes that read it (lets us skip absent fields fast)
    _nodes_by_field: dict[str, list[int]] = field(default_factory=dict)
    # Rules that cannot be soundly bounded -> always considered by the engine.
    _always_candidate_rules: frozenset[int] = field(default_factory=frozenset)
    pass_through: bool = False
    fields: frozenset[str] = field(default_factory=frozenset)

    # construction

    @classmethod
    def from_rules(
        cls, rules: Iterable[Any], extractor: PredicateExtractor | None = None
    ) -> PredicateIndex:
        """Build an index from rules using the shared sound extractor."""
        extractor = extractor or PredicateExtractor()
        return cls.from_predicate_set(extractor.from_rules(rules))

    @classmethod
    def from_predicate_set(cls, ps: PredicateSet) -> PredicateIndex:
        index = cls(
            pass_through=ps.has_unfilterable_rule,
            fields=frozenset(ps.fields),
            _always_candidate_rules=frozenset(ps.always_candidate_rules),
        )
        # Even when some rules are unfilterable (pass_through=True) we STILL build
        # the alpha nodes for the *filterable* clauses. ``matches`` will
        # short-circuit to True, but ``candidate_rule_ids`` uses these to prune
        # the filterable majority - the real win on mixed rule sets.
        node_cache: dict[tuple[str, str, Any], int] = {}
        # signature tuple -> mutable set of rule ids sharing it
        sig_to_rules: dict[tuple[int, ...], set[int]] = {}
        for clause in ps.filterable_clauses:
            node_ids = sorted(index._intern_node(pred, node_cache) for pred in clause.must.values())
            if not node_ids:
                continue
            sig = tuple(node_ids)
            sig_to_rules.setdefault(sig, set()).add(clause.rule_id)
        for sig, rule_ids in sig_to_rules.items():
            index._signatures.append(sig)
            index._signature_rules.append(frozenset(rule_ids))
        logger.info(
            "predicate index: %d distinct signatures, %d distinct alpha nodes over "
            "%d fields (%d always-candidate, pass_through=%s)",
            len(index._signatures),
            len(index._nodes),
            len(index._nodes_by_field),
            len(index._always_candidate_rules),
            index.pass_through,
        )
        return index

    def _intern_node(self, pred: LeafPredicate, node_cache: dict[tuple[str, str, Any], int]) -> int:
        value_key = _hashable(pred.value)
        key = (pred.field, pred.op, value_key)
        existing = node_cache.get(key)
        if existing is not None:
            return existing
        node = _AlphaNode(
            field=pred.field,
            op=pred.op,
            value_key=value_key,
            test=_make_test(pred.op, pred.value),
        )
        node_id = len(self._nodes)
        self._nodes.append(node)
        node_cache[key] = node_id
        self._nodes_by_field.setdefault(pred.field, []).append(node_id)
        return node_id

    # streaming screen

    def _eval_nodes(self, fact: dict[str, Any]) -> list[bool]:
        """Evaluate every distinct alpha node once for this fact."""
        get = fact.get
        return [node.test(get(node.field, _MISSING)) for node in self._nodes]

    @property
    def signature_count(self) -> int:
        """Number of distinct necessary-condition signatures in the index.

        This is the per-fact cost of the alpha scan (each signature is checked
        once). A small count relative to the rule universe means the alpha layer
        is cheap and high-leverage - the basis for the adaptive engage decision.
        """
        return len(self._signatures)

    @property
    def filterable_rule_count(self) -> int:
        """How many rules contribute at least one sound necessary condition."""
        return sum(len(rs) for rs in self._signature_rules)

    @property
    def can_prune(self) -> bool:
        """Whether the index can ever drop a rule (i.e. has filterable signatures).

        When False, every rule is unfilterable / pass-through and the alpha scan
        could only ever return the full universe - so it should be skipped.
        """
        return bool(self._signatures)

    def matches(self, fact: dict[str, Any]) -> bool:
        """Return True if ``fact`` could satisfy the necessary conditions of any rule.

        Evaluates each *distinct* alpha node at most once, then checks signatures.
        ``O(distinct predicates + distinct signatures)`` per fact.
        """
        if self.pass_through:
            return True
        node_results = self._eval_nodes(fact)
        for sig in self._signatures:
            if all(node_results[nid] for nid in sig):
                return True
        return False

    def candidate_rule_ids(self, fact: dict[str, Any], universe: Iterable[int]) -> set[int]:
        """Return the subset of ``universe`` whose alpha conditions ``fact`` passes.

        This is the **alpha layer** for engine integration: given the rules the
        engine would otherwise evaluate (``universe``), drop those whose
        necessary conditions provably fail for this fact. Rules that are
        unfilterable (no sound bound) are always kept - soundness over speed.

        Fast path: if *every* signature passes, no rule can be pruned, so the
        universe is returned without any set work. The expensive per-rule union
        only happens when pruning is actually possible.

        Returns a set ⊆ ``universe``. Guaranteed superset of the rules that can
        actually fire (no false negatives).
        """
        universe = universe if isinstance(universe, (set, frozenset)) else set(universe)
        if not self._signatures:
            # Nothing filterable -> cannot prune anything soundly.
            return set(universe)
        node_results = self._eval_nodes(fact)
        sig_pass = [all(node_results[nid] for nid in sig) for sig in self._signatures]
        if all(sig_pass):
            # No signature failed -> nothing to prune. Avoid all set ops.
            return set(universe)
        kept: set[int] = set()
        for passed, rule_ids in zip(sig_pass, self._signature_rules):
            if passed:
                kept |= rule_ids
        kept |= self._always_candidate_rules
        return kept & universe

    def prune(self, fact: dict[str, Any], universe: list[int]) -> list[int]:
        """Engine-facing prune: like :meth:`candidate_rule_ids` but allocation-light.

        Returns the *same list object* when nothing can be pruned (the common
        all-match worst case), so the hot path pays no set/list copy. Otherwise
        returns a new pruned list preserving ``universe`` order.
        """
        if not self._signatures:
            return universe
        node_results = self._eval_nodes(fact)
        sig_pass = [all(node_results[nid] for nid in sig) for sig in self._signatures]
        if all(sig_pass):
            return universe  # nothing pruned -> reuse caller's list, zero copy
        keep: set[int] = set()
        for passed, rule_ids in zip(sig_pass, self._signature_rules):
            if passed:
                keep |= rule_ids
        keep |= self._always_candidate_rules
        return [rid for rid in universe if rid in keep]

    def filter(self, facts: Iterable[dict[str, Any]]) -> Iterator[dict[str, Any]]:
        """Stream only the candidate facts - never materializes the input."""
        match = self.matches
        for fact in facts:
            if match(fact):
                yield fact


def _hashable(value: Any) -> Any:
    """Best-effort hashable key for predicate-value dedup."""
    if isinstance(value, (list, set)):
        return tuple(value)
    try:
        hash(value)
    except TypeError:
        return repr(value)
    return value
