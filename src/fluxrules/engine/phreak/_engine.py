"""PhreakEngine - PHREAK evaluation with integrated optimizations.

Internal implementation module - not part of public API.

Lazy evaluation via field-based dirty tracking. Implements the PHREAK
evaluation strategy with integrated optimizations:

- Lazy evaluation: only evaluate rules whose segments are dirty
- Dirty tracking: track which fields changed
- Field indexing: efficient lookup of affected rules
- Segment network: hierarchical rule organization
"""

from __future__ import annotations

import concurrent.futures
import logging
import threading
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from fluxrules.engine.base import BaseEngine
from fluxrules.engine.configuration import EngineConfig, get_config
from fluxrules.engine.infrastructure.bitmask_linker import BitMaskLinker
from fluxrules.engine.infrastructure.engine_metrics import EngineMetrics
from fluxrules.engine.infrastructure.lazy_evaluation import LazyEvaluationMixin
from fluxrules.engine.infrastructure.node_memory import NodeMemory
from fluxrules.engine.infrastructure.scope_guard import enforce_single_fact_boundary
from fluxrules.engine.operators import evaluate_operator
from fluxrules.engine.phreak.condition_compiler import (
    CompiledCondition,
    compile_condition,
)
from fluxrules.prefilter import PredicateIndex

if TYPE_CHECKING:
    from fluxrules.engine.infrastructure import EvaluationFilter

logger = logging.getLogger(__name__)


# Sentinel for "field absent" in NodeMemory cache keys.
# Using a unique object distinguishes a missing field from a field whose value
# is None, since operators behave differently based on field_present.
_ABSENT = object()

# Sentinel meaning "this value cannot be used in a memo key".
# Returned by _hashable() for unhashable values (lists, dicts) so the leaf memo
# can safely bypass caching for those leaves instead of raising.
_UNHASHABLE = object()


class _AlphaStats:
    """Running prune statistics for the alpha pre-filter.

    Cheap counters maintained on the hot path so the engine can report, without
    a profiler attached:

    - how many candidate rules entered the alpha layer (``candidates_in``),
    - how many survived it (``candidates_out``),
    - the candidate count of the most recent fact (``last_in`` / ``last_out``),
    - how many facts were processed (``facts``) and how many times the alpha
      scan was actually run vs. bypassed (``engaged`` / ``bypassed``).

    The cumulative prune ratio = ``1 - candidates_out / candidates_in`` is the
    headline "is the alpha layer pulling its weight" metric. See benchmarks.md
    for performance details and typical prune ratios.
    """

    __slots__ = (
        "bypassed",
        "candidates_in",
        "candidates_out",
        "engaged",
        "facts",
        "last_in",
        "last_out",
    )

    def __init__(self) -> None:
        self.reset()

    def reset(self) -> None:
        self.candidates_in = 0
        self.candidates_out = 0
        self.facts = 0
        self.engaged = 0
        self.bypassed = 0
        self.last_in = 0
        self.last_out = 0

    def record(self, n_in: int, n_out: int, *, engaged: bool) -> None:
        self.facts += 1
        self.candidates_in += n_in
        self.candidates_out += n_out
        self.last_in = n_in
        self.last_out = n_out
        if engaged:
            self.engaged += 1
        else:
            self.bypassed += 1

    @property
    def prune_ratio(self) -> float:
        """Cumulative fraction of candidate rules dropped by the alpha layer."""
        if self.candidates_in == 0:
            return 0.0
        return 1.0 - (self.candidates_out / self.candidates_in)

    def as_dict(self) -> dict[str, Any]:
        return {
            "facts": self.facts,
            "candidates_in": self.candidates_in,
            "candidates_out": self.candidates_out,
            "engaged_facts": self.engaged,
            "bypassed_facts": self.bypassed,
            "last_candidates_in": self.last_in,
            "last_candidates_out": self.last_out,
            "prune_ratio": self.prune_ratio,
        }


def _hashable(value: Any) -> Any:
    """Return a hashable representation of ``value`` for memo keys.

    Lists/sets are converted to tuples/frozensets; dicts to sorted item tuples.
    Anything that still cannot be hashed yields the ``_UNHASHABLE`` sentinel so
    callers can disable memoization for that leaf rather than crash.
    """
    try:
        hash(value)
        return value
    except TypeError:
        pass
    try:
        if isinstance(value, (list, tuple)):
            return tuple(_hashable(v) for v in value)
        if isinstance(value, (set, frozenset)):
            return frozenset(_hashable(v) for v in value)
        if isinstance(value, dict):
            return tuple(sorted((k, _hashable(v)) for k, v in value.items()))
    except TypeError:
        return _UNHASHABLE
    return _UNHASHABLE


def _dsl_linker_safe(dsl: Any) -> bool:
    """Whether the presence linker may narrow candidacy by this rule's fields.

    The presence linker assumes a rule needs *all* its referenced fields present
    to fire. That holds only for a **pure conjunction of leaves** (AND / nested
    AND). An ``or`` node needs only one branch's fields, and a ``not`` node
    matches when its field is *absent* - so for either the linker would unsoundly
    drop a rule whose fields are partly absent (F1 and the OR-branch variant).
    Such rules must stay candidates and be decided by the sound alpha pre-filter
    plus full evaluation.

    A rule with no ``condition_dsl`` carries a flat conjunction of ``conditions``
    and so is linker-safe.
    """
    if dsl is None:
        return True
    if not isinstance(dsl, dict):
        return False
    ctype = dsl.get("type")
    if ctype in (None, "condition"):
        return True
    if ctype == "and":
        children = dsl.get("children") or dsl.get("conditions") or []
        return bool(children) and all(_dsl_linker_safe(child) for child in children)
    if ctype in ("group", "composite"):
        logic = str(dsl.get("logic") or dsl.get("op") or "AND").upper()
        if logic != "AND":
            return False
        children = dsl.get("children") or dsl.get("conditions") or []
        return bool(children) and all(_dsl_linker_safe(child) for child in children)
    # or / not / exists / accumulate / cross-fact: presence is not necessary.
    return False


class PhreakEngine(LazyEvaluationMixin, BaseEngine):
    """PHREAK engine with lazy evaluation and integrated optimizations.

    Inherits from:
    - LazyEvaluationMixin: Provides lazy evaluation strategy (dirty tracking, segment identification)
    - BaseEngine: Shared infrastructure (repository, indices, working memory)

    Characteristics:
    - Lazy evaluation (only process changed facts / dirty segments)
    - Dirty tracking (track field modifications via FieldIndex)
    - Field indexing (find affected rules efficiently)
    - Segment network (hierarchical rule organization)
    - Conflict resolution (agenda-based, salience + recency)

    Ideal for:
    - Streaming data (facts arriving incrementally)
    - Large numbers of facts with few changes
    - Complex rule dependencies
    - When latency matters more than throughput

    Note: This engine uses the Strategy Pattern via mixins. PhreakEngine
    adds LazyEvaluationMixin for dirty tracking and segment-based optimization
    on top of BaseEngine.
    """

    def __init__(
        self,
        max_rules: int = 50_000,
        config: EngineConfig | None = None,
        streaming_mode: bool = False,
        alpha_prefilter: bool = True,
        compile_conditions: bool = False,
        strict_scope: bool = False,
        strict_discovery: bool = False,
        enable_metrics: bool = False,
    ) -> None:
        """Initialize PhreakEngine.

        The MRO (Method Resolution Order) ensures proper initialization:
        PhreakEngine → LazyEvaluationMixin → BaseEngine → ABC → object

        Args:
            max_rules: Maximum rules to handle
            config: EngineConfig instance. If None, uses get_config()
            streaming_mode: If True, enable lazy evaluation with dirty tracking.

                When False (default): Evaluate all applicable rules on each call
                (consistent results, no caching).

                When True: Only re-evaluate when input facts change
                (optimized for streaming data with repeated fact sets).

                Use streaming_mode=True when:
                - Processing streaming/real-time data with incremental updates
                - Same facts are evaluated multiple times
                - Latency matters more than throughput
                - Working with large rule sets and small fact changes

                Example::

                    engine = PhreakEngine(streaming_mode=True)
                    engine.load_rules(rules)

                    # First evaluation: all matching rules evaluated
                    result = engine.evaluate({"age": 25})

                    # Second evaluation with same facts: returns empty
                    # (results cached from first evaluation)
                    result = engine.evaluate({"age": 25})

                    # Third evaluation with changed facts: re-evaluates
                    result = engine.evaluate({"age": 30})

                Contract - unchanged facts return EMPTY:
                    In streaming mode ``evaluate()`` reports the *delta* of
                    activations since the last call. If the incoming fact is
                    identical to the previous evaluation (including a no-op
                    delete of an already-absent field), the result's
                    ``fired_rules`` is empty because those activations were
                    already delivered. Stateless mode, by contrast, re-fires
                    every matching rule on every call. When comparing the two
                    modes for equivalence, only compare on cycles where the fact
                    actually changed (see
                    ``TestStreamingDeltaLinkingParity`` for the correct gate).
                    For genuine fact changes - including real field additions and
                    removals that alter matching - streaming results equal
                    stateless results exactly.
            alpha_prefilter: If True (default), build the value-aware alpha
                ``PredicateIndex`` at load time and use it as the primary
                per-fact candidate reducer (P1.1). Set False for A/B parity
                testing (``alpha_on`` ≡ ``alpha_off`` fired sets).
            compile_conditions: Opt-in per-rule condition compilation (off by
                default; see the attribute note below).
            strict_scope: P0.3 single-fact boundary guardrail. When True,
                ``load_rules`` raises on cross-fact / temporal rule shapes.
            strict_discovery: P1.2 parity switch. When True, the legacy
                ``TokenPropagator`` discovery runs alongside the single
                linker+alpha discovery and the two candidate sets are asserted
                equal (CI use). Off in production so the redundant O(segments)
                scan is never paid per fact.
            enable_metrics: P2.4 operational observability. When True, the
                engine records leaf-memo hit/miss, per-fact linked-rule count,
                and per-fact eval latency into a lightweight ``EngineMetrics``
                collector exposed via :meth:`get_observability_metrics`. Off by
                default so the hot path is unaffected (the recorders are no-ops
                when disabled). Advisory only - never affects ``fired_rules``.
        """
        super().__init__(max_rules=max_rules)
        self._config = config or get_config()
        self._streaming_mode = streaming_mode

        # Single-fact boundary enforcement (P0.3). When True, ``load_rules``
        # raises on rule shapes that imply cross-fact / temporal semantics the
        # engine cannot honor; when False (default) it logs a warning so misuse
        # is visible without breaking existing callers.
        self._strict_scope = strict_scope

        # Discovery parity switch (P1.2). When True, the legacy O(segments)
        # ``TokenPropagator`` discovery is run alongside the single
        # linker+alpha discovery path and the two candidate sets are asserted to
        # agree (used in CI to prove the refactor preserves behavior). Off in
        # production: only the single discovery path executes, so the propagator
        # scan is not paid per fact.
        self._strict_discovery = strict_discovery

        # Operational observability (P2.4). When True, instantiate the
        # lightweight ``EngineMetrics`` collector and record leaf-memo hit/miss,
        # per-fact linked-rule count, and per-fact eval latency. Flag-gated so
        # the default hot path pays nothing (the recorders are no-ops when the
        # collector is None). Advisory only - never affects ``fired_rules``.
        self._enable_metrics = enable_metrics
        self._metrics: EngineMetrics | None = EngineMetrics() if enable_metrics else None

        # In-memory alpha pre-filter. Built once from the rule set at
        # load time; on every fact it cheaply drops rules whose necessary
        # conditions provably fail BEFORE the costly condition evaluation. Sound
        # (no false negatives): unfilterable rules are always kept. Disable via
        # ``alpha_prefilter=False`` for A/B comparison and parity testing.
        #
        # P1.1: the alpha index is the *primary* candidate reducer - it is
        # value-aware (the bit-mask linker only checks field *presence*), so it
        # is the component that actually prunes on the common workload where
        # every fact carries the hot field. It runs *first*, before the linker's
        # presence narrowing, and is engaged by an adaptive, selectivity-driven
        # decision (``_alpha_should_engage``) rather than a hardcoded rule-count
        # gate.
        self._alpha_prefilter_enabled = alpha_prefilter
        self._alpha_index: PredicateIndex | None = None
        # Adaptive engage decision (replaces the old static ``>= 64 matched
        # rules`` gate). The alpha scan costs O(distinct signatures); it pays off
        # when signatures are few relative to the rule universe (high condition
        # sharing => cheap scan, high prune payoff). We engage when the index can
        # prune at all AND the signature scan is cheap relative to the candidate
        # set it would otherwise hand to per-rule evaluation. Computed once at
        # load time into ``_alpha_engage`` (a pure function of the built index)
        # so the hot path pays only a bool check.
        self._alpha_engage = False
        # Running prune statistics (feeds P2 observability and the P1.3
        # benchmark): cumulative candidates seen by / surviving the alpha layer,
        # plus per-fact before/after of the most recent evaluation.
        self._alpha_stats = _AlphaStats()

        # Field-bearing universe for the single discovery path (P1.2). Populated
        # in ``_register_with_bitmask_linker`` at load time; initialized empty so
        # ``evaluate`` before ``load_rules`` is well-defined (no candidates).
        self._field_bearing_rule_ids: list[int] = []
        self._field_bearing_rule_id_set: frozenset[int] = frozenset()

        # Rules the presence linker must not narrow: any rule that is not a pure
        # conjunction of leaves (contains or/not), because presence of all its
        # fields is then not necessary to fire (F1 and the OR-branch variant).
        self._linker_unsafe_rule_ids: frozenset[int] = frozenset()

        # Per-rule condition compilation. Each rule's condition tree
        # is compiled once at load time into a ``fn(facts) -> bool`` closure that
        # inlines the boolean structure, replacing the recursive dict-walk in
        # ``_evaluate_condition_inner`` on the hot path. Leaves still delegate to
        # ``evaluate_operator`` (exact same semantics; no string eval) via a
        # memo-aware leaf compiler that shares the per-cycle leaf cache. Falls
        # back to the interpreter for ``accumulate`` / unknown nodes. Disable via
        # ``compile_conditions=False`` for A/B parity testing.
        #
        # DEFAULT OFF (data-driven): benchmarking (perf_condition_compiler)
        # shows it is *sound* but not faster - once the leaf memo collapses
        # the ~96% of leaf evaluations shared across rules, structural inlining
        # has almost nothing left to win, and the closure indirection slightly
        # regresses single-leaf rules (0.90x). Kept as opt-in infrastructure;
        # the real remaining cost is per-rule framework overhead and rule count,
        # which the alpha pre-filter (C.1) addresses by cutting rules evaluated.
        self._compile_conditions_enabled = compile_conditions
        self._compiled_conditions: dict[int, CompiledCondition] = {}

        # Initialize BitMaskLinker for O(1) rule linking
        self._bitmask_linker = BitMaskLinker()

        # Initialize NodeMemory for streaming mode caching. The LRU bound is
        # configurable via EngineConfig (P2.3).
        self._node_memory: NodeMemory | None = None
        if streaming_mode:
            self._node_memory = NodeMemory(
                max_entries=getattr(self._config, "node_memory_max_entries", 100_000)
            )

        # First streaming evaluation must run in full even when no segment is
        # dirty, so a NOT-rule that fires on an absent field surfaces on first
        # sight (F1). Later identical evaluations still short-circuit to an empty
        # delta.
        self._streaming_first_eval = True

        # Cache the set of fields each rule depends on.
        # Computed once at load time so the hot evaluation path never has to
        # call segment_network.get_segments_for_rule(rid) per matched rule.
        self._rule_relevant_fields_cache: dict[int, tuple[str, ...]] = {}

        # Per-cycle leaf-condition memo - THREAD-LOCAL.
        # Many rules share identical leaf conditions (field, op, value). Within a
        # single evaluation cycle the facts are constant, so a leaf result can be
        # reused across every rule that references it. The memo lives in
        # thread-local storage (not a plain instance attribute) so that
        # concurrent stateless ``evaluate()`` calls on a *single shared engine*
        # never clobber each other's per-cycle cache. Each thread gets its own
        # ``_thread_local.leaf_memo``: a fresh dict on the sequential path, or
        # ``None`` on the parallel path (where a plain dict would not be safe
        # across the worker threads it spawns). Provably result-preserving: it
        # only memoizes a pure function of (field, op, value, facts).
        self._thread_local = threading.local()

    # Evaluation contract (P2.5)

    @property
    def mode(self) -> str:
        """The live evaluation contract: ``"streaming"`` or ``"stateless"``.

        Surfaced so operators can see *which contract is active* (P2.5):

        - ``"stateless"`` - ``evaluate`` re-fires **every** matching rule on
          **every** call (a pure function of ``(rules, facts)``). Safe behind a
          request/response HTTP path and freely load-balanced.
        - ``"streaming"`` - ``evaluate`` returns the **activation delta** since
          the previous call (keyed on the prior facts). Repeated facts return an
          **empty** ``fired_rules``. This is **order-dependent** and requires
          **sticky routing** (the same stream must hit the same engine instance,
          in order). Using it behind a stateless, load-balanced HTTP path is a
          misuse - see ``docs/sessions.md`` and ``docs/working-memory.md``.
        """
        return "streaming" if self._streaming_mode else "stateless"

    # Thread-local per-cycle leaf memo accessor

    @property
    def _leaf_memo(self) -> dict[tuple, bool] | None:
        """The current thread's per-cycle leaf memo (``None`` if disabled).

        Backed by thread-local storage so concurrent stateless ``evaluate()``
        calls on a shared engine never share or clobber this scratch dict.
        """
        return getattr(self._thread_local, "leaf_memo", None)

    @_leaf_memo.setter
    def _leaf_memo(self, value: dict[tuple, bool] | None) -> None:
        self._thread_local.leaf_memo = value

    # Rule loading with BitMaskLinker registration

    def load_rules(self, rules: list[Any]) -> None:
        """Load rules into the unified rule space.

        Overrides BaseEngine.load_rules to register segments and rules
        with the BitMaskLinker for O(1) rule activation checks.

        Args:
            rules: List of Rule objects or rule dicts to load
        """
        # Single-fact boundary guardrail (P0.3). Warn by default, raise when
        # ``strict_scope=True``, on rule shapes that imply cross-fact / temporal
        # semantics this engine cannot honor. Done before building the network so
        # strict callers fail fast.
        enforce_single_fact_boundary(rules, strict=self._strict_scope)

        # Call parent to populate repository, segments, and field index
        super().load_rules(rules)

        # Register all segments and rules with BitMaskLinker
        self._register_with_bitmask_linker()

        # A reloaded rule set is a fresh evaluation state: force a full first
        # streaming pass (F1).
        self._streaming_first_eval = True

    def _register_with_bitmask_linker(self) -> None:
        """Register all loaded segments and rules with the BitMaskLinker.

        This builds the bit-mask linking structure for O(1) rule activation.
        Also precomputes each rule's relevant-field tuple for fast cache keys.
        """
        # Clear previous registrations
        self._bitmask_linker.clear()
        self._rule_relevant_fields_cache.clear()

        # Register each segment with a unique bit position
        for seg_id, segment in self.segment_network.segments.items():
            self._bitmask_linker.register_segment(seg_id, segment.fields)

        # Register each rule with its required segments and precompute the
        # sorted tuple of fields it depends on (so condition cache keys never
        # recompute it per fact).
        for rule_id in self.rule_repository.rules:
            segments = self.segment_network.get_segments_for_rule(rule_id)
            segment_ids = [seg.segment_id for seg in segments]
            self._bitmask_linker.register_rule(rule_id, segment_ids)
            relevant_fields: set[str] = set()
            for seg in segments:
                relevant_fields.update(seg.fields)
            self._rule_relevant_fields_cache[rule_id] = tuple(sorted(relevant_fields))

        # Field-bearing universe (P1.2). The single discovery path operates over
        # the rules that carry at least one condition field - exactly the rules
        # the legacy ``TokenPropagator`` could ever discover. Rules with no
        # fields (empty condition / always-true) are excluded here to preserve
        # the historical behavior that ``evaluate`` does not surface them as
        # candidates (the propagator's affected-segment scan never reached an
        # empty-field segment). Kept as a list (stable order) + set (O(1)
        # membership) so discovery never rescans the repository per fact.
        self._field_bearing_rule_ids = [
            rid for rid, flds in self._rule_relevant_fields_cache.items() if flds
        ]
        self._field_bearing_rule_id_set = frozenset(self._field_bearing_rule_ids)

        # Rules that are not a pure conjunction of leaves (or/not) must bypass
        # the presence linker: some referenced fields may legitimately be absent
        # when the rule fires (F1 and the OR-branch variant).
        self._linker_unsafe_rule_ids = frozenset(
            rid
            for rid, rule in self.rule_repository.rules.items()
            if not _dsl_linker_safe(getattr(rule, "condition_dsl", None))
        )

        # (Re)build the in-memory alpha pre-filter from the current
        # rule set. Done once per load, never per fact.
        if self._alpha_prefilter_enabled:
            rules = list(self.rule_repository.rules.values())
            self._alpha_index = PredicateIndex.from_rules(rules)
        else:
            self._alpha_index = None

        # P1.1: decide *once* whether to engage the alpha scan, from measured
        # index selectivity rather than a hardcoded rule-count gate. Reset the
        # running prune stats for the new rule set.
        self._alpha_engage = self._compute_alpha_engage(self._alpha_index)
        self._alpha_stats.reset()

        # (Re)compile each rule's condition tree into a closure.
        # Done once per load; the interpreter is captured as the fallback for
        # accumulate / unknown nodes so results never change.
        self._compiled_conditions = {}
        if self._compile_conditions_enabled:
            for rid, rule in self.rule_repository.rules.items():
                condition = getattr(rule, "condition_dsl", None)
                if not isinstance(condition, dict):
                    continue
                self._compiled_conditions[rid] = compile_condition(
                    condition,
                    self._config,
                    fallback_factory=self._make_interpreter_fallback,
                    leaf_compiler=self._compile_memo_leaf,
                )

    @staticmethod
    def _compute_alpha_engage(index: PredicateIndex | None) -> bool:
        """Adaptive engage decision for the alpha pre-filter (P1.1).

        Replaces the old static ``len(matched_rule_ids) >= 64`` gate with a
        decision driven by the index's *measured selectivity*, computed once at
        load time:

        - If there is no index or it can never prune (every rule is
          unfilterable / pass-through with no filterable signatures), engaging
          would only ever scan and return the full universe -> **skip**.
        - Otherwise the per-fact scan costs ``O(distinct signatures)``. It pays
          off when signatures are few relative to the rules they gate (high
          condition sharing => cheap scan, high prune payoff). We engage when the
          index can prune at all, because ``prune`` already short-circuits with
          zero set work on the all-signatures-pass fact (so a low-selectivity
          workload degrades to a cheap O(signatures) scan, not O(rules) of set
          ops), and auto-bypasses copying when nothing is pruned.

        Engaging on *capability to prune* (rather than a magic rule count) is
        what makes the alpha layer the **primary** reducer instead of a throttled
        secondary one.
        """
        if index is None:
            return False
        # ``can_prune`` is True iff the index holds at least one filterable
        # signature - i.e. there exists a fact that would drop a rule. When
        # False, every rule is always-candidate and the scan is pure overhead.
        return index.can_prune

    # Observability-aware evaluate wrapper (P2.4)

    def evaluate(
        self,
        facts: dict[str, Any],
        filters: EvaluationFilter | None = None,
        *,
        strict_facts: bool = False,
    ) -> Any:
        """Evaluate ``facts``, recording per-fact latency when metrics are on.

        Thin wrapper over :meth:`BaseEngine.evaluate`: when ``enable_metrics``
        is True it feeds the result's measured ``latency_ms`` into the
        observability reservoir (p50/p95/p99). When metrics are off this is a
        direct passthrough with no added cost beyond one bool check.
        """
        result = super().evaluate(facts, filters, strict_facts=strict_facts)
        if self._metrics is not None:
            self._metrics.record_latency_ms(result.latency_ms)
        return result

    # Single discovery path (P1.2)

    def _candidate_rule_ids(
        self,
        facts: dict[str, Any],
        filters: EvaluationFilter | None = None,
    ) -> list[int]:
        """The **one** per-fact discovery path for PhreakEngine (P1.2).

        Overrides ``BaseEngine._candidate_rule_ids`` so that ``evaluate`` no
        longer runs the O(segments) ``TokenPropagator`` scan and then has
        ``_evaluate_rules`` independently recompute + intersect a second
        candidate set. Instead, candidates are produced **once** here, directly
        from the value-aware alpha index (primary, P1.1) and the presence-only
        bit-mask linker (secondary), and handed to ``_evaluate_rules`` as-is.

        Pipeline (stateless mode - the concurrency-safe production path):

        1. Start from the **field-bearing universe** (rules with ≥1 condition
           field). This exactly reproduces which rules the legacy propagator
           could ever surface: no-field / always-true rules were never reached
           by its affected-segment scan and so are not candidates.
        2. **Alpha first** (primary reducer): drop rules whose necessary leaf
           conditions provably fail for this fact. Value-aware - this is the
           component that actually prunes on the common workload where every
           fact carries the hot field.
        3. **Linker second** (secondary narrow): keep only alpha survivors whose
           required field *presence* holds, via the pure, side-effect-free
           :meth:`BitMaskLinker.linked_subset_for` (no shared-state mutation, so
           concurrent ``evaluate`` on one engine is safe - the P0.2 contract).

        Streaming mode keeps the incremental, mutating delta-linker (single
        stream owned by one thread by contract) and then applies alpha.

        The result equals the old reconciliation ``propagator ∩ linker ∩ alpha``
        exactly: for any field-bearing rule the linker (all required segments
        present) is a subset of the propagator (any segment present), so the
        propagator term is redundant. ``strict_discovery=True`` asserts this
        equivalence in CI.
        """
        present_fields = frozenset(facts.keys())

        if self._streaming_mode:
            # Incremental, stateful delta-linking (single-stream by contract).
            self._bitmask_linker.update_facts_delta(facts)
            linked = self._bitmask_linker.get_linked_rules()
            # field-bearing ∩ linked, plus linker-unsafe rules (or/not) which can
            # fire with some fields absent and so must bypass the presence linker.
            candidates: list[int] = [
                rid
                for rid in self._field_bearing_rule_ids
                if rid in linked or rid in self._linker_unsafe_rule_ids
            ]
            n_in = len(candidates)
            engaged = self._alpha_engage and self._alpha_index is not None
            if engaged and self._alpha_index is not None:
                candidates = self._alpha_index.prune(facts, candidates)
        else:
            # Stateless: alpha-first (primary) then a pure presence narrow.
            candidates = self._field_bearing_rule_ids
            n_in = len(candidates)
            engaged = self._alpha_engage and self._alpha_index is not None
            if engaged and self._alpha_index is not None:
                candidates = self._alpha_index.prune(facts, candidates)
            linked_ids = self._bitmask_linker.linked_subset_for(present_fields, candidates)
            if self._linker_unsafe_rule_ids:
                # Keep alpha-surviving or/not rules the presence linker would drop.
                linked_set = set(linked_ids)
                candidates = [
                    rid
                    for rid in candidates
                    if rid in linked_set or rid in self._linker_unsafe_rule_ids
                ]
            else:
                candidates = linked_ids

        # Record before/after-alpha prune stats (P1.1 observability / P1.3).
        self._alpha_stats.record(n_in, len(candidates), engaged=engaged)

        if filters:
            candidates = self._apply_filters(candidates, filters)

        # Per-fact linked-rule count for P2.4 (sanity vs the alpha candidate
        # count). Recorded only when metrics are enabled (no-op otherwise).
        if self._metrics is not None:
            self._metrics.record_linked(len(candidates))

        # Optional CI parity guard: prove the single path == the old
        # propagator ∩ linker ∩ alpha reconciliation. Off in production.
        if self._strict_discovery:
            self._assert_discovery_parity(facts, present_fields, candidates, filters)

        return candidates

    def _assert_discovery_parity(
        self,
        facts: dict[str, Any],
        present_fields: frozenset[str],
        single_path: list[int],
        filters: EvaluationFilter | None,
    ) -> None:
        """Assert the single discovery path == legacy ``propagator ∩ linker ∩ alpha``.

        Used only when ``strict_discovery=True`` (CI / debugging). Recomputes the
        retired reconciliation and compares candidate *sets*. Raises
        ``AssertionError`` on any divergence so a behavior change can never slip
        through unnoticed.
        """
        # Legacy path 1: token propagator over affected segments.
        affected = self.get_affected_segments(facts)
        propagator = set(self.token_propagator.propagate(facts, affected))
        # Legacy path 2: pure presence linker over all rules.
        linker = self._bitmask_linker.linked_rules_for(present_fields)
        reconciled = propagator & linker
        # Legacy path 3: alpha prune over the reconciliation.
        if self._alpha_engage and self._alpha_index is not None:
            reconciled = set(self._alpha_index.prune(facts, list(reconciled)))
        # or/not rules bypass the presence linker (F1 + OR-branch variant);
        # mirror that here so parity reflects the corrected contract.
        if self._linker_unsafe_rule_ids:
            alpha_surviving = set(self._field_bearing_rule_ids)
            if self._alpha_engage and self._alpha_index is not None:
                alpha_surviving = set(
                    self._alpha_index.prune(facts, list(self._field_bearing_rule_ids))
                )
            reconciled |= alpha_surviving & self._linker_unsafe_rule_ids
        if filters:
            reconciled = set(self._apply_filters(list(reconciled), filters))
        if set(single_path) != reconciled:
            raise AssertionError(
                "strict_discovery parity failed: single path "
                f"{sorted(single_path)} != reconciled {sorted(reconciled)} "
                f"for facts={facts}"
            )

    # Pre-filter observability (P1.1 step 4 / P2)

    def get_prefilter_stats(self) -> dict[str, Any]:
        """Return cumulative alpha pre-filter prune statistics.

        Exposes the running counters the engine maintains on the hot path so
        callers (the P1.3 benchmark, P2 observability, an SRE dashboard) can see
        whether the alpha layer is actually reducing candidates:

        - ``enabled`` / ``engaged``: is the alpha index built, and did the
          adaptive gate (P1.1) decide to run it for this rule set (a bool).
        - ``signature_count`` / ``filterable_rule_count`` / ``pass_through``:
          shape of the built index (selectivity inputs).
        - ``facts`` / ``candidates_in`` / ``candidates_out`` / ``prune_ratio``:
          cumulative per-fact candidate counts before/after the alpha layer.
        - ``engaged_facts`` / ``bypassed_facts``: how many facts ran vs. skipped
          the alpha scan.
        - ``last_candidates_in`` / ``last_candidates_out``: the most recent fact.

        ``prune_ratio`` is the headline number: the fraction of candidate rules
        dropped by alpha before per-rule condition evaluation.

        Concurrency note: the counters are **advisory**. Under the P0.2 shared-
        engine contract they may race across threads (a counter increment can be
        lost), but they never affect ``fired_rules`` - only the linker query
        (kept pure) and the thread-local leaf memo determine results. Read stats
        from a quiesced engine for exact numbers, or one engine per worker.
        """
        stats: dict[str, Any] = {
            "enabled": self._alpha_prefilter_enabled,
            "engaged": self._alpha_engage,
            "field_bearing_rules": len(self._field_bearing_rule_ids),
        }
        index = self._alpha_index
        if index is not None:
            stats["signature_count"] = index.signature_count
            stats["filterable_rule_count"] = index.filterable_rule_count
            stats["pass_through"] = index.pass_through
            stats["can_prune"] = index.can_prune
        stats.update(self._alpha_stats.as_dict())
        return stats

    def reset_prefilter_stats(self) -> None:
        """Zero the running alpha prune counters (e.g. between benchmark runs)."""
        self._alpha_stats.reset()

    # Operational observability (P2.4)

    def get_observability_metrics(self) -> dict[str, Any]:
        """Return the consolidated operational metrics for this engine (P2.4).

        Merges the signals an operator needs to *see* the documented failure
        modes in production, from the components that own them:

        - ``candidates_per_fact`` (pre/post alpha) + ``alpha_prune_ratio`` -
          from the alpha pre-filter stats. A collapsing prune ratio means a hot
          field is defeating the primary filter (→ O(rules)/fact).
        - ``leaf_memo_hit_rate`` - cross-rule leaf sharing effectiveness.
        - ``node_memory`` hit rate / evictions - streaming cache value (only in
          streaming mode; ``None`` otherwise).
        - ``linked_rules`` (last / avg) - sanity vs the candidate count.
        - ``eval_latency_ms`` p50/p95/p99 - SLO tracking.
        - ``working_memory_size`` - leak detection (should stay near-zero for
          pure stateless scoring).

        Engine-rebuild events live at the ``RuleEnginePool`` layer (P0.1) and are
        merged in by the API adapter, not here (one engine instance does not see
        its own rebuilds).

        Returns ``{"enabled": False}`` when the engine was built without
        ``enable_metrics=True`` for everything except the always-available alpha
        prune stats and working-memory size (which are cheap and already tracked
        regardless of the metrics flag).
        """
        prefilter = self.get_prefilter_stats()
        facts_seen = max(1, prefilter.get("facts", 0) or 0)
        metrics: dict[str, Any] = {
            "enabled": self._enable_metrics,
            "mode": "streaming" if self._streaming_mode else "stateless",
            "rules_loaded": len(self.rule_repository),
            "segments": len(self.segment_network.segments),
            "working_memory_size": len(self.working_memory),
            "working_memory_high_water_mark": self.working_memory.high_water_mark,
            # Always-available alpha signals (tracked regardless of the flag).
            "alpha_prune_ratio": prefilter.get("prune_ratio", 0.0),
            "alpha_engaged": prefilter.get("engaged", False),
            "candidates_per_fact_in": prefilter.get("candidates_in", 0) / facts_seen,
            "candidates_per_fact_out": prefilter.get("candidates_out", 0) / facts_seen,
            "last_candidates_in": prefilter.get("last_candidates_in", 0),
            "last_candidates_out": prefilter.get("last_candidates_out", 0),
        }
        # NodeMemory (streaming only).
        if self._node_memory is not None:
            ns = self._node_memory.stats
            metrics["node_memory"] = {
                "hit_rate": ns["hit_rate"],
                "entries": ns["entries"],
                "max_entries": ns["max_entries"],
                "evictions": ns["evictions"],
            }
        else:
            metrics["node_memory"] = None
        # Flag-gated hot-path metrics (leaf memo, linked rules, latency).
        if self._metrics is not None:
            metrics.update(self._metrics.as_dict())
        return metrics

    def reset_observability_metrics(self) -> None:
        """Zero the flag-gated observability counters (alpha stats untouched)."""
        if self._metrics is not None:
            self._metrics.reset()

    # Concrete evaluation strategy

    def _evaluate_rules(
        self,
        rule_ids: list[int],
        facts: dict[str, Any],
    ) -> tuple[list[int], list[str], dict[int, str]]:
        """PHREAK evaluation with lazy segment-based optimization.

        Single-discovery contract (P1.2): ``rule_ids`` is the *final* candidate
        set produced by :meth:`_candidate_rule_ids` (field-bearing universe →
        alpha → linker). This method no longer re-runs the bit-mask linker, the
        alpha prune, or an O(N) ``rid in rule_ids`` reconciliation - those were
        the redundant second discovery path. It only sorts by priority and
        evaluates.

        In streaming mode the candidate set is the incremental delta-linker's
        (also alpha-narrowed) output; the per-cycle bookkeeping below
        (``affected_segments`` for the explanation string, ``_update_prev_facts``)
        is unchanged.

        Args:
            rule_ids: Final candidate rule IDs from the single discovery path.
            facts: Dictionary of facts to evaluate

        Returns:
            Tuple of (fired_rule_ids, actions, explanations)
        """
        fired: list[int] = []
        actions: list[str] = []
        explanations: dict[int, str] = {}

        # Start a fresh per-cycle leaf memo for THIS thread. The sequential
        # path uses it; the parallel path disables it (sets None) for thread
        # safety. Stored thread-locally so concurrent stateless evaluate() calls
        # on a shared engine never share or leak state across each other.
        self._leaf_memo = {}

        # Streaming mode: a no-change cycle (no dirty segments) returns the empty
        # delta, exactly as before. Discovery (delta-linker + alpha) already ran
        # in ``_candidate_rule_ids``; here we only need the dirty-segment set for
        # agenda unscheduling and the cached-empty short-circuit.
        if self._streaming_mode:
            affected_segments = self._identify_dirty_segments(facts)

            # Agenda unscheduling - cancel rules affected by changes.
            if affected_segments and hasattr(self, "agenda"):
                self._cancel_affected_activations(facts)

            if not affected_segments and not self._streaming_first_eval:
                # No fields changed in streaming mode - return cached result.
                self._update_prev_facts(facts)
                return fired, actions, explanations
            self._streaming_first_eval = False
        else:
            # Stateless mode: the affected-segment set (used only to render the
            # explanation string) is the union of the candidates' segments.
            affected_segments = set()
            get_segments = self.segment_network.get_segments_for_rule
            for rid in rule_ids:
                for seg in get_segments(rid):
                    affected_segments.add(seg.segment_id)

        # Build the (priority, rid, rule) tuples directly from the final
        # candidate set. No linker re-run, no alpha re-prune, no membership
        # reconciliation - ``rule_ids`` is already the discovered candidate set.
        rules_with_priority = []
        repo_get = self.rule_repository.get
        for rid in rule_ids:
            rule = repo_get(rid)
            if rule:
                rules_with_priority.append((rule.priority, rid, rule))

        rules_with_priority.sort(key=lambda x: (x[0], x[1]), reverse=True)

        # Evaluate using sequential or parallel path
        threshold = self._config.parallel_threshold
        if len(rules_with_priority) > threshold:
            fired, actions, explanations = self._evaluate_parallel(
                rules_with_priority, facts, affected_segments
            )
        else:
            fired, actions, explanations = self._evaluate_sequential(
                rules_with_priority, facts, affected_segments
            )

        # Step 4: Update dirty tracking for next evaluation (streaming mode only)
        if self._streaming_mode:
            self._update_prev_facts(facts)

        return fired, actions, explanations

    def _cancel_affected_activations(self, facts: dict[str, Any]) -> None:
        """Cancel pending activations for rules affected by fact changes.

        When facts change, cancel activations for affected rules.
        """
        if not self._prev_facts:
            changed_fields = set(facts.keys())
        else:
            current_fields = set(facts.keys())
            prev_fields = set(self._prev_facts.keys())
            changed_fields = current_fields ^ prev_fields
            for field in current_fields & prev_fields:
                if facts[field] != self._prev_facts.get(field):
                    changed_fields.add(field)

        if changed_fields and hasattr(self, "agenda"):
            affected_rules: set[int] = set()
            for field in changed_fields:
                field_rules = self.field_index._field_to_rules.get(field, set())
                affected_rules.update(field_rules)
            for rule_id in affected_rules:
                self.agenda.cancel_activation(rule_id)

    # Sequential / parallel evaluation helpers

    def _build_condition_cache_key(
        self,
        rid: int,
        facts: dict[str, Any],
    ) -> tuple:
        """Build a hashable cache key using only fields the rule depends on.

        Uses the precomputed ``_rule_relevant_fields_cache``
        instead of calling ``segment_network.get_segments_for_rule(rid)`` on
        every invocation, removing a per-rule lookup from the hot path.
        """
        relevant_fields = self._rule_relevant_fields_cache.get(rid)
        if relevant_fields is None:
            # Fallback for rules registered outside the normal load path.
            rule_segments = self.segment_network.get_segments_for_rule(rid)
            field_set: set[str] = set()
            for seg in rule_segments:
                field_set.update(seg.fields)
            relevant_fields = tuple(sorted(field_set))
        return (
            rid,
            tuple((k, facts.get(k)) for k in relevant_fields if k in facts),
        )

    def _evaluate_sequential(
        self,
        rules_with_priority: list[tuple],
        facts: dict[str, Any],
        affected_segments: set[str],
    ) -> tuple[list[int], list[str], dict[int, str]]:
        """Evaluate rules sequentially with per-cycle condition caching.

        Flat evaluation: every candidate rule's root condition is evaluated in
        priority order. (A prior hierarchical-segment skip path was removed in
        P2.1 - no rule was ever mapped to a parent segment, so the skip branch
        never fired while costing two extra per-rule scans.)
        """
        fired: list[int] = []
        actions: list[str] = []
        explanations: dict[int, str] = {}

        seg_info = ", ".join(sorted(affected_segments)) if affected_segments else "all"

        # In stateless mode the NodeMemory cache in _evaluate_condition is
        # never consulted, so bind _eval_root directly and shed one call frame
        # per rule. Streaming mode keeps the cache-aware wrapper.
        if self._streaming_mode:
            eval_condition: Callable[[dict[str, Any], dict[str, Any], int | None], bool] = (
                self._evaluate_condition
            )
        else:
            eval_condition = self._eval_root
        for _prio, rid, rule in rules_with_priority:
            if eval_condition(rule.condition_dsl, facts, rid):
                fired.append(rid)
                # Extend with every action, not just the first: a rule may
                # carry several and dropping the rest would silently lose them.
                actions.extend(rule.actions)
                explanations[rid] = (
                    f"Rule {rule.name} ({rid}) matched via PHREAK (segments: {seg_info})"
                )
        return fired, actions, explanations

    def _evaluate_parallel(
        self,
        rules_with_priority: list[tuple],
        facts: dict[str, Any],
        affected_segments: set[str],
    ) -> tuple[list[int], list[str], dict[int, str]]:
        """Parallel condition evaluation for large matched rule sets.

        Uses ThreadPoolExecutor since _evaluate_condition is a pure
        function (reads immutable facts + rule DSL, no shared mutable state).
        executor.map preserves input order so priority ordering is maintained.
        """
        # Disable the per-cycle leaf memo on the parallel path.
        # A plain dict is not safe for concurrent writes across worker threads,
        # and the parallel path already deduplicates via its own condition_cache.
        self._leaf_memo = None

        fired: list[int] = []
        actions: list[str] = []
        explanations: dict[int, str] = {}

        seg_info = ", ".join(sorted(affected_segments)) if affected_segments else "all"

        def _eval_one(
            item: tuple,
        ) -> tuple[int, Any, bool]:
            _prio, rid, rule = item
            cache_key = self._build_condition_cache_key(rid, facts)
            cached = condition_cache.get(cache_key)
            if cached is not None:
                return rid, rule, cached
            result = self._evaluate_condition(rule.condition_dsl, facts, rid)
            condition_cache[cache_key] = result
            return rid, rule, result

        condition_cache: dict[tuple, bool] = {}
        workers = self._config.parallel_workers
        with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as executor:
            results = list(executor.map(_eval_one, rules_with_priority))

        for rid, rule, matched in results:
            if matched:
                fired.append(rid)
                actions.extend(rule.actions)
                explanations[rid] = (
                    f"Rule {rule.name} ({rid}) matched via PHREAK (segments: {seg_info})"
                )
        return fired, actions, explanations

    # Condition evaluation (reuses comparison module)

    def _evaluate_condition(
        self,
        condition: dict[str, Any],
        facts: dict[str, Any],
        rule_id: int | None = None,
    ) -> bool:
        # Check NodeMemory cache in streaming mode
        # Key the cache on the stable rule_id and only the
        # field values the rule actually depends on (relevant_values). This
        # replaces the previous key built from id(condition) (unstable across
        # rule reloads) plus the entire fact set (which almost never produced
        # a cross-fact hit). Building the key from relevant values lets facts
        # that differ only in irrelevant fields share a cache entry.
        if self._node_memory is not None and self._streaming_mode and rule_id is not None:
            relevant_fields = self._rule_relevant_fields_cache.get(rule_id)
            if relevant_fields is not None:
                relevant_values = tuple(
                    facts[f] if f in facts else _ABSENT for f in relevant_fields
                )
                try:
                    hash(relevant_values)
                except TypeError:
                    # An unhashable fact value (e.g. a list used with `contains`)
                    # cannot key the memo. Caching is an optimization, so skip it
                    # and evaluate directly - the result is identical.
                    return self._eval_root(condition, facts, rule_id)
                cached_result = self._node_memory.get(rule_id, "root", relevant_values)
                if cached_result is not None:
                    return cached_result

                result = self._eval_root(condition, facts, rule_id)
                self._node_memory.put(rule_id, "root", relevant_values, result)
                return result

        # No caching available (stateless mode, no rule_id, or unregistered rule)
        return self._eval_root(condition, facts, rule_id)

    def _eval_root(
        self,
        condition: dict[str, Any],
        facts: dict[str, Any],
        rule_id: int | None,
    ) -> bool:
        """Evaluate a rule's root condition, preferring the compiled closure.

        when the rule was compiled at load time, use its closure
        (inlined boolean structure); otherwise fall back to the recursive
        interpreter. Results are identical by construction.
        """
        if rule_id is not None:
            compiled = self._compiled_conditions.get(rule_id)
            if compiled is not None:
                return compiled(facts)
        return self._evaluate_condition_inner(condition, facts)

    def _make_interpreter_fallback(self, condition: dict[str, Any]) -> CompiledCondition:
        """Capture the interpreter as a closure for non-compilable subtrees."""
        return lambda facts: self._evaluate_condition_inner(condition, facts)

    def _compile_memo_leaf(self, condition: dict[str, Any], flags: Any) -> CompiledCondition:
        """Compile a leaf into a **memo-aware** closure.

        the compiled boolean structure must not regress below the
        interpreter, whose dominant win is the per-cycle leaf memo (identical
        ``(field, op, value)`` leaves shared across rules are evaluated once).
        This closure hoists the constants (field, op, value, value hashability)
        out of the per-fact path, then consults ``self._leaf_memo`` exactly like
        :meth:`_eval_leaf`. When the memo is disabled (parallel path) it degrades
        to a direct ``evaluate_operator`` call. Results are identical to the
        interpreter by construction.
        """
        field = condition.get("field", "")
        op = condition.get("op", "==")
        value = condition.get("value")
        value_key = _hashable(value)
        snh = flags.strict_null_handling
        stc = flags.strict_type_comparison
        bsc = flags.boolean_string_coercion
        # If the rule-side value is unhashable it can never be memoized; bake a
        # direct-eval closure so the per-fact path skips the memo bookkeeping.
        value_memoizable = value_key is not _UNHASHABLE

        def _leaf(facts: dict[str, Any]) -> bool:
            present = field in facts
            fact_val = facts.get(field)
            memo = self._leaf_memo
            if memo is not None and value_memoizable:
                fact_key = _hashable(fact_val)
                if fact_key is not _UNHASHABLE:
                    memo_key = (field, op, value_key, present, fact_key)
                    cached = memo.get(memo_key)
                    if cached is not None:
                        if self._metrics is not None:
                            self._metrics.record_leaf(hit=True)
                        return cached
                    if self._metrics is not None:
                        self._metrics.record_leaf(hit=False)
                    result = evaluate_operator(
                        op,
                        fact_val,
                        value,
                        field_present=present,
                        strict_null_handling=snh,
                        strict_type_comparison=stc,
                        boolean_string_coercion=bsc,
                    )
                    memo[memo_key] = result
                    return result
            return evaluate_operator(
                op,
                fact_val,
                value,
                field_present=present,
                strict_null_handling=snh,
                strict_type_comparison=stc,
                boolean_string_coercion=bsc,
            )

        return _leaf

    def _evaluate_condition_inner(
        self,
        condition: dict[str, Any],
        facts: dict[str, Any],
    ) -> bool:
        """Inner evaluation logic (without caching)."""
        if not isinstance(condition, dict):
            return False
        ctype = condition.get("type")
        if ctype == "condition":
            return self._eval_leaf(condition, facts)
        if ctype in ("composite", "group", "and", "or"):
            if ctype == "and":
                logic = "AND"
            elif ctype == "or":
                logic = "OR"
            else:
                logic = (condition.get("logic") or condition.get("op", "AND")).upper()
            children = condition.get("conditions") or condition.get("children") or []
            results = [self._evaluate_condition_inner(c, facts) for c in children]
            return all(results) if logic == "AND" else any(results)
        if ctype == "not":
            inner = condition.get("condition")
            if inner:
                return not self._evaluate_condition_inner(inner, facts)
            inner_list = condition.get("conditions", [])
            if inner_list:
                return not any(self._evaluate_condition_inner(c, facts) for c in inner_list)
            return True
        if ctype == "exists":
            field = condition.get("field")
            if field:
                return field in facts and facts[field] is not None
            inner = condition.get("condition")
            return self._evaluate_condition_inner(inner, facts) if inner else False
        if ctype == "accumulate":
            return self._eval_accumulate(condition, facts)
        return False

    def _eval_leaf(
        self,
        condition: dict[str, Any],
        facts: dict[str, Any],
    ) -> bool:
        field = condition.get("field", "")
        op = condition.get("op", "==")
        value = condition.get("value")

        # Per-cycle leaf memo. Reuse the result for identical
        # (field, op, value) leaves already evaluated this cycle. Only active on
        # the sequential path (parallel path leaves the memo as None for thread
        # safety). The memo key includes the present-value so it is exact.
        memo = self._leaf_memo
        if memo is not None:
            present = field in facts
            fact_val = facts.get(field)
            value_key = _hashable(value)
            fact_key = _hashable(fact_val)
            if value_key is not _UNHASHABLE and fact_key is not _UNHASHABLE:
                memo_key = (field, op, value_key, present, fact_key)
                cached = memo.get(memo_key)
                if cached is not None:
                    if self._metrics is not None:
                        self._metrics.record_leaf(hit=True)
                    return cached
                if self._metrics is not None:
                    self._metrics.record_leaf(hit=False)
                result = evaluate_operator(
                    op,
                    fact_val,
                    value,
                    field_present=present,
                    strict_null_handling=self._config.strict_null_handling,
                    strict_type_comparison=self._config.strict_type_comparison,
                    boolean_string_coercion=self._config.boolean_string_coercion,
                )
                memo[memo_key] = result
                return result

        return evaluate_operator(
            op,
            facts.get(field),
            value,
            field_present=field in facts,
            strict_null_handling=self._config.strict_null_handling,
            strict_type_comparison=self._config.strict_type_comparison,
            boolean_string_coercion=self._config.boolean_string_coercion,
        )

    def _eval_accumulate(
        self,
        condition: dict[str, Any],
        facts: dict[str, Any],
    ) -> bool:
        field = condition.get("field", "")
        threshold = condition.get("threshold", 0)
        op = condition.get("op", ">=")
        val = facts.get(field)
        if val is None:
            return False
        agg = float(val) if isinstance(val, (int, float)) else 0
        return evaluate_operator(
            op,
            agg,
            threshold,
            field_present=True,
            strict_null_handling=False,
            strict_type_comparison=False,
            boolean_string_coercion=False,
        )

    # Action-aware evaluation

    async def evaluate_with_actions(
        self,
        facts: dict[str, Any],
    ) -> tuple:
        """Evaluate rules and execute resulting actions.

        Args:
            facts: Facts to evaluate against rules.

        Returns:
            Tuple of (EvaluationResult, list[ActionExecutionResult])
        """
        from fluxrules.domain.actions import ActionExecutionEngine

        result = self.evaluate(facts)

        # Parse string actions into typed Actions
        action_engine = ActionExecutionEngine()
        actions = [action_engine.parse_action_string(a) for a in result.actions]

        # Execute actions
        action_results = await action_engine.execute_actions(actions)

        return result, action_results
