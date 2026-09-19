"""PreFilteredEvaluator - orchestrates indexed pre-filter -> engine evaluation.

Loads facts into an indexed store, screens them with rule-derived predicates,
and evaluates only the survivors with the engine. Reports how much work the
pre-filter saved.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from fluxrules.prefilter.predicate import PredicateExtractor, PredicateSet

if TYPE_CHECKING:  # pragma: no cover - avoids importing SQLAlchemy at core import
    from fluxrules.prefilter.sql_store import FactPreFilterStore

logger = logging.getLogger(__name__)


@dataclass
class PreFilterStats:
    """Outcome metrics for a pre-filtered run."""

    total_facts: int = 0
    candidate_facts: int = 0
    evaluated_facts: int = 0
    fired_facts: int = 0
    load_seconds: float = 0.0
    filter_seconds: float = 0.0
    evaluate_seconds: float = 0.0
    unfilterable: bool = False
    fields_indexed: int = 0

    @property
    def reduction_ratio(self) -> float:
        """Fraction of facts eliminated before engine evaluation (0..1)."""
        if self.total_facts == 0:
            return 0.0
        return 1.0 - (self.candidate_facts / self.total_facts)


@dataclass
class PreFilteredEvaluator:
    """Run an engine over a fact stream, pre-screening with an indexed store.

    Args:
        engine: any object exposing ``rule_repository.rules`` and ``evaluate``.
        store: indexed fact store (SQLite Dev / Postgres Prod).
        extractor: predicate extractor (defaults to a fresh one).
    """

    engine: Any
    store: FactPreFilterStore
    extractor: PredicateExtractor = field(default_factory=PredicateExtractor)
    _predicates: PredicateSet | None = field(default=None, init=False)

    def predicates(self) -> PredicateSet:
        if self._predicates is None:
            rules = list(self.engine.rule_repository.rules.values())
            self._predicates = self.extractor.from_rules(rules)
        return self._predicates

    def run(self, facts: Iterable[dict[str, Any]]) -> tuple[list[Any], PreFilterStats]:
        """Materialize all facts, pre-filter, and evaluate survivors.

        Returns ``(results, stats)`` where ``results`` are the engine
        ``EvaluationResult`` objects for candidate facts that fired ≥1 rule.
        """
        facts = list(facts)
        stats = PreFilterStats(total_facts=len(facts))
        preds = self.predicates()
        stats.unfilterable = preds.has_unfilterable_rule
        stats.fields_indexed = len(preds.fields)

        t0 = time.perf_counter()
        self.store.ensure_schema(preds.fields)
        load = self.store.bulk_load(facts)
        stats.load_seconds = time.perf_counter() - t0
        stats.fields_indexed = load.fields_indexed

        results: list[Any] = []
        t1 = time.perf_counter()
        candidates = list(self.store.candidates(preds))
        stats.filter_seconds = time.perf_counter() - t1
        stats.candidate_facts = len(candidates)

        t2 = time.perf_counter()
        for fact in candidates:
            res = self.engine.evaluate(fact)
            stats.evaluated_facts += 1
            if res.fired_rules:
                stats.fired_facts += 1
                results.append(res)
        stats.evaluate_seconds = time.perf_counter() - t2

        logger.info(
            "prefilter: %d facts -> %d candidates (%.1f%% eliminated) -> %d fired",
            stats.total_facts,
            stats.candidate_facts,
            stats.reduction_ratio * 100,
            stats.fired_facts,
        )
        return results, stats

    def iter_candidates(self, facts: Iterable[dict[str, Any]]) -> Iterator[dict[str, Any]]:
        """Stream candidate facts (load + filter) without evaluating."""
        facts = list(facts)
        preds = self.predicates()
        self.store.ensure_schema(preds.fields)
        self.store.bulk_load(facts)
        yield from self.store.candidates(preds)
