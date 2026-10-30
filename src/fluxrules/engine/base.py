"""BaseEngine - shared infrastructure for the PHREAK engine and custom engines.

Provides rule repository, segment network, field index, working memory,
token propagator, and agenda so that concrete engines only implement
their evaluation *strategy*.

Usage:
    from fluxrules.engine.base import BaseEngine
"""

from __future__ import annotations

import logging
import time
from abc import ABC, abstractmethod
from collections import defaultdict
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from fluxrules.engine.infrastructure import (
    Agenda,
    ConflictResolutionStrategy,
    EvaluationFilter,
    EvaluationResult,
    FieldIndex,
    GlobalRuleRepository,
    SalienceRecencyStrategy,
    SegmentNetwork,
    TokenPropagator,
    UnifiedWorkingMemory,
)

if TYPE_CHECKING:
    from fluxrules.domain.unified_rule import Rule

logger = logging.getLogger(__name__)


class BaseEngine(ABC):
    """Base class providing unified infrastructure for all engines.

    The concrete engine (PhreakEngine) extends this class
    and only implements ``_evaluate_rules()``. Custom engines may also
    subclass it.

    All infrastructure - rule repository, segment network, field index,
    working memory, token propagator, agenda - is shared.
    """

    # Class-level defaults so subclasses that skip ``BaseEngine.__init__`` keep
    # working: no schema, no per-fact validation.
    _fact_schema_info: Any = None
    _fact_intake: Any = None
    _fact_pipeline: Callable[[dict[str, Any]], dict[str, Any]] | None = None

    def __init__(
        self,
        max_rules: int = 50_000,
        *,
        deployment_config: object | None = None,
        id_generator: object | None = None,
        fact_schema: type | None = None,
        validate_facts: str = "off",
        on_invalid: str = "raise",
        fact_pipeline: Callable[[dict[str, Any]], dict[str, Any]] | None = None,
    ) -> None:
        from fluxrules.engine.configuration import get_config
        from fluxrules.facts import (
            ON_INVALID_MODES,
            VALIDATE_FACTS_MODES,
            _FactIntake,
            schema_info,
        )
        from fluxrules.utils.id_generators import RuleIDGenerator

        # Typed facts. ``fact_schema`` checks rule fields at load time (no
        # per-fact cost); ``validate_facts`` adds opt-in per-fact validation and
        # normalization before discovery.
        if validate_facts not in VALIDATE_FACTS_MODES:
            raise ValueError(
                f"validate_facts must be one of {VALIDATE_FACTS_MODES}, got {validate_facts!r}"
            )
        if on_invalid not in ON_INVALID_MODES:
            raise ValueError(f"on_invalid must be one of {ON_INVALID_MODES}, got {on_invalid!r}")
        if validate_facts != "off" and fact_schema is None:
            raise ValueError(f"validate_facts={validate_facts!r} requires fact_schema=")
        self._fact_schema_info = schema_info(fact_schema) if fact_schema is not None else None
        self._fact_intake = (
            _FactIntake(self._fact_schema_info, validate_facts, on_invalid)
            if self._fact_schema_info is not None and validate_facts != "off"
            else None
        )
        # Fact pipeline: reshapes each fact in ``evaluate`` before validation.
        self._fact_pipeline = fact_pipeline

        # Working-memory high-water mark (P2.3): configurable via EngineConfig so
        # operators can tune the leak watchdog without code changes.
        _cfg = get_config()
        _wm_high_water = getattr(_cfg, "working_memory_high_water_mark", 100_000)

        # Unified infrastructure
        self.rule_repository = GlobalRuleRepository(max_rules=max_rules)
        self.segment_network = SegmentNetwork(max_rules=max_rules)
        self.field_index = FieldIndex()
        self.working_memory = UnifiedWorkingMemory(
            fact_ttl_ms=3_600_000,
            high_water_mark=_wm_high_water,
        )
        self.token_propagator = TokenPropagator(
            segment_network=self.segment_network,
            working_memory=self.working_memory,
        )
        self.agenda = Agenda()
        self.conflict_strategy: ConflictResolutionStrategy = SalienceRecencyStrategy()
        self._is_stateful = True

        # ID generator setup
        if id_generator is not None:
            self.id_generator = id_generator
        elif deployment_config is not None:
            self.id_generator = RuleIDGenerator.from_config(deployment_config)
        else:
            self.id_generator = RuleIDGenerator()

    # Rule management

    def load_rules(self, rules: list[Rule | dict[str, Any]]) -> None:
        """Load rules into the unified rule space.

        Accepts canonical :class:`fluxrules.Rule` objects or dicts; everything
        is normalised to ``Rule`` by the repository, so the engine sees exactly
        one type.

        Populates rule_repository, segment_network, and field_index.

        Raises:
            UnknownFieldError: when the engine has a ``fact_schema`` and a rule
                references a field the schema lacks. Nothing is loaded.
        """
        if self._fact_schema_info is not None:
            self._fact_schema_info.check_rules(rules)
        self.rule_repository.add_rules(rules)
        self.segment_network.add_rules(rules)
        self.field_index.build_from_rules(rules)
        logger.info(
            "Loaded %d rules, created %d segments",
            len(rules),
            len(self.segment_network),
        )

    def add_rule(self, rule: Rule | dict[str, Any]) -> None:
        """Add a single rule incrementally.

        Convenience alias over :meth:`load_rules` so every engine exposes the
        same trio (``load_rules`` / ``add_rule`` / ``add_rules``). Engines that
        maintain extra per-rule state override this.
        """
        self.add_rules([rule])

    def add_rules(self, rules: list[Rule | dict[str, Any]]) -> None:
        """Add multiple rules incrementally (additive, not a replacement).

        Delegates to :meth:`load_rules`, which merges into the existing rule
        space rather than clearing it.
        """
        self.load_rules(rules)

    # Fact management

    def assert_fact(self, fact: Any) -> str:
        """Assert a fact into unified working memory. Returns fact_id.

        A model is converted with :func:`fluxrules.facts.to_fact_dict`, as in
        :meth:`evaluate`. It is not validated against ``fact_schema``: working
        memory is not read by ``evaluate``, and ``validate_facts`` applies only
        to ``evaluate``.
        """
        if type(fact) is not dict:
            from fluxrules.facts import to_fact_dict

            fact = to_fact_dict(fact)
        return self.working_memory.assert_fact(fact)

    def retract_fact(self, fact_id: str) -> None:
        """Retract a fact from working memory."""
        self.working_memory.retract_fact(fact_id)

    # Implicit discovery

    def get_affected_segments(self, facts: dict[str, Any]) -> set[str]:
        """Segments affected by the fact's fields."""
        return self.field_index.get_affected_segments(facts)

    def discover_rules(
        self,
        facts: dict[str, Any],
        filters: EvaluationFilter | None = None,
    ) -> list[int]:
        """Discover which rules apply to the given facts (no IDs needed).

        1. Find affected segments via field index.
        2. Propagate tokens to collect matching rule IDs.
        3. Apply optional filters.
        """
        affected = self.get_affected_segments(facts)
        matched = self.token_propagator.propagate(facts, affected)
        if filters:
            matched = self._apply_filters(matched, filters)
        return matched

    def _candidate_rule_ids(
        self,
        facts: dict[str, Any],
        filters: EvaluationFilter | None = None,
    ) -> list[int]:
        """Strategy hook: candidate rule IDs to consider for ``facts``.

        This is the single discovery entry point used by :meth:`evaluate`.
        The base implementation uses token propagation
        (:meth:`discover_rules`); concrete engines may override it with a
        cheaper, engine-specific discovery (e.g. PhreakEngine uses its bit-mask
        linker directly to avoid a redundant O(segments) propagator scan).
        """
        return self.discover_rules(facts, filters=filters)

    # Public evaluation API

    @property
    def fact_schema(self) -> type | None:
        """The model class rules are checked against, or ``None``."""
        info = self._fact_schema_info
        return info.model if info is not None else None

    @property
    def quarantined_facts(self) -> list[Any]:
        """Facts rejected under ``on_invalid="quarantine"`` (oldest first, bounded).

        Each entry is a :class:`fluxrules.facts.QuarantinedFact` holding the
        original input and the :class:`~fluxrules.domain.errors.FactValidationError`.
        """
        return list(self._fact_intake.quarantine) if self._fact_intake is not None else []

    def evaluate(
        self,
        facts: Any,
        filters: EvaluationFilter | None = None,
        *,
        strict_facts: bool = False,
    ) -> EvaluationResult:
        """Evaluate facts against all loaded rules (no ID needed).

        Concrete engines implement ``_evaluate_rules()`` for their
        specific strategy; everything else is shared.

        Args:
            facts: Input facts: a flat ``dict``, or a Pydantic model, dataclass,
                attrs class or msgspec ``Struct`` (converted with
                :func:`fluxrules.facts.to_fact_dict`; nested models become
                dotted keys). With ``fact_pipeline`` set, the fact dict is first
                passed through it. With ``validate_facts`` enabled, the dict is
                then validated against ``fact_schema``.
            filters: Optional rule filter constraints.
            strict_facts: When ``True``, perform a structural pre-flight check
                (dict type, string keys, flat values) before discovery.
                Defaults to ``False`` to keep hot-path overhead off unless
                explicitly requested.

        Raises:
            FactValidationError: when validation is on, the fact is invalid and
                ``on_invalid="raise"``. With ``"skip"`` or ``"quarantine"`` the
                fact is dropped and an empty result is returned.

        A fact the pipeline drops (a ``Filter`` / ``DropFact``, or a transform
        whose error policy skips the record) also returns an empty result.
        Any other pipeline error propagates.
        """
        if self._fact_pipeline is not None:
            from fluxrules.pipeline.core import _SkipRecord
            from fluxrules.pipeline.transforms.composed import DropFact

            if type(facts) is not dict:
                from fluxrules.facts import to_fact_dict

                facts = to_fact_dict(facts)
            try:
                facts = self._fact_pipeline(facts)
            except (_SkipRecord, DropFact):
                return EvaluationResult(engine_type=type(self).__name__)

        if self._fact_intake is not None:
            admitted = self._fact_intake.admit(facts)
            if admitted is None:
                return EvaluationResult(engine_type=type(self).__name__)
            facts = admitted
        elif type(facts) is not dict:
            from fluxrules.facts import to_fact_dict

            try:
                facts = to_fact_dict(facts)
            except TypeError:
                if strict_facts:
                    # Report through the structural contract (InvalidFactError).
                    from fluxrules.pipeline.validators import FactValidator

                    FactValidator.validate("engine.evaluate", facts)
                raise

        if strict_facts:
            from fluxrules.pipeline.validators import FactValidator

            FactValidator.validate("engine.evaluate", facts)

        start = time.time()

        # Step 1: discover applicable rules (engine-specific strategy hook).
        candidate_rule_ids = self._candidate_rule_ids(facts, filters=filters)

        # Step 2: delegate to concrete engine strategy
        fired_rules, actions, explanations = self._evaluate_rules(
            candidate_rule_ids,
            facts,
        )

        # Step 3: group by domain/tag
        rules_by_domain = self._group_by_domain(fired_rules)
        rules_by_tag = self._group_by_tag(fired_rules)

        latency_ms = (time.time() - start) * 1000
        return EvaluationResult(
            candidate_rule_ids=candidate_rule_ids,
            fired_rules=fired_rules,
            rules_by_domain=rules_by_domain,
            rules_by_tag=rules_by_tag,
            fired_segments=list(self.get_affected_segments(facts)),
            latency_ms=latency_ms,
            engine_type=type(self).__name__,
            actions=actions,
            explanations=explanations,
        )

    # Convenience methods

    def evaluate_by_domain(
        self,
        facts: dict[str, Any],
        domains: list[str],
    ) -> EvaluationResult:
        return self.evaluate(facts, filters=EvaluationFilter(domains=frozenset(domains)))

    def evaluate_by_tags(
        self,
        facts: dict[str, Any],
        tags: list[str],
    ) -> EvaluationResult:
        return self.evaluate(facts, filters=EvaluationFilter(tags=frozenset(tags)))

    def evaluate_all(self, facts: dict[str, Any]) -> EvaluationResult:
        return self.evaluate(facts, filters=None)

    # Configuration

    def set_conflict_strategy(self, strategy: ConflictResolutionStrategy) -> None:
        self.conflict_strategy = strategy
        self.agenda.set_strategy(strategy)

    # Stats / lifecycle

    def get_stats(self) -> dict[str, Any]:
        segs = self.segment_network.segments
        return {
            "engine_type": type(self).__name__,
            "rules_loaded": len(self.rule_repository),
            "segments_created": len(segs),
            "facts_in_memory": len(self.working_memory),
            "field_index_entries": len(self.field_index),
            "average_rules_per_segment": (
                sum(len(s.rule_ids) for s in segs.values()) / len(segs) if segs else 0
            ),
        }

    def clear(self) -> None:
        self.rule_repository.clear()
        self.segment_network.clear()
        self.field_index.clear()
        self.working_memory.clear()
        self.agenda.clear()

    # Abstract - concrete engines implement this

    @abstractmethod
    def _evaluate_rules(
        self,
        rule_ids: list[int],
        facts: dict[str, Any],
    ) -> tuple[list[int], list[str], dict[int, str]]:
        """Evaluate the given rules against facts.

        Returns:
            (fired_rule_ids, actions, explanations)
        """
        ...

    # Protected helpers

    def _apply_filters(
        self,
        rule_ids: list[int],
        filters: EvaluationFilter,
    ) -> list[int]:
        filtered = rule_ids
        if filters.domains:
            filtered = [
                r
                for r in filtered
                if (rule := self.rule_repository.get(r)) and rule.domain in filters.domains
            ]
        if filters.tags:
            filtered = [
                r
                for r in filtered
                if (rule := self.rule_repository.get(r)) and (filters.tags & rule.tags)
            ]
        if filters.min_priority is not None:
            filtered = [
                r
                for r in filtered
                if (rule := self.rule_repository.get(r)) and rule.priority >= filters.min_priority
            ]
        if filters.max_priority is not None:
            filtered = [
                r
                for r in filtered
                if (rule := self.rule_repository.get(r)) and rule.priority <= filters.max_priority
            ]
        return filtered

    def _group_by_domain(self, rule_ids: list[int]) -> dict[str, list[int]]:
        grouped: dict[str, list[int]] = defaultdict(list)
        for rid in rule_ids:
            rule = self.rule_repository.get(rid)
            if rule:
                grouped[rule.domain].append(rid)
        return dict(grouped)

    def _group_by_tag(self, rule_ids: list[int]) -> dict[str, list[int]]:
        grouped: dict[str, list[int]] = defaultdict(list)
        for rid in rule_ids:
            rule = self.rule_repository.get(rid)
            if rule:
                for tag in rule.tags:
                    grouped[tag].append(rid)
        return dict(grouped)
