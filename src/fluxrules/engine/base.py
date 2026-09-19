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

    def __init__(
        self,
        max_rules: int = 50_000,
        *,
        deployment_config: object | None = None,
        id_generator: object | None = None,
    ) -> None:
        from fluxrules.engine.configuration import get_config
        from fluxrules.utils.id_generators import RuleIDGenerator

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
        """
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

    def assert_fact(self, fact: dict[str, Any]) -> str:
        """Assert a fact into unified working memory. Returns fact_id."""
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

    def evaluate(
        self,
        facts: dict[str, Any],
        filters: EvaluationFilter | None = None,
        *,
        strict_facts: bool = False,
    ) -> EvaluationResult:
        """Evaluate facts against all loaded rules (no ID needed).

        Concrete engines implement ``_evaluate_rules()`` for their
        specific strategy; everything else is shared.

        Args:
            facts: Input fact mapping to evaluate.
            filters: Optional rule filter constraints.
            strict_facts: When ``True``, perform a structural pre-flight check
                (dict type, string keys, flat values) before discovery.
                Defaults to ``False`` to keep hot-path overhead off unless
                explicitly requested.
        """
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
