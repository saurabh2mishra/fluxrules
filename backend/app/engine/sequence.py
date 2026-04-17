from __future__ import annotations

from bisect import bisect_right
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Sequence, Tuple

from app.config import settings
from app.engine.comparison import evaluate_operator


@dataclass(frozen=True)
class _FactRecord:
    """Internal fact container sorted by inserted_at and ingestion order."""

    fact_id: int
    payload: Dict[str, Any]
    inserted_at: datetime


class SequenceEvaluator:
    """Evaluate ordered multi-step sequences over asserted facts.

    The evaluator is incremental: every new assertion only tries to complete
    sequences where the new fact can satisfy the final step. This avoids
    re-evaluating all partial sequences on every insert.
    """

    def __init__(
        self,
        *,
        steps: Sequence[Dict[str, Any]],
        within_window_seconds: int | None = None,
        correlate_on: Sequence[str] | None = None,
    ) -> None:
        if not steps:
            raise ValueError("steps must not be empty")

        self.steps = list(steps)
        self.within_window_seconds = within_window_seconds
        self.correlate_on = list(correlate_on or [])

        self._facts_sorted: List[_FactRecord] = []
        self._fact_times: List[datetime] = []
        self._next_fact_id = 1
        self._emitted_signatures: set[Tuple[int, ...]] = set()

    def assert_fact(self, fact: Dict[str, Any]) -> List[List[Dict[str, Any]]]:
        """Assert a new fact and return only newly completed sequences."""
        record = self._store_fact(fact)

        # Optimization: only attempt completion when new fact matches final step.
        if not self._matches_step(record.payload, self.steps[-1]):
            return []

        completed = self._find_completions_ending_at(record)
        results: List[List[Dict[str, Any]]] = []

        for records in completed:
            signature = tuple(rec.fact_id for rec in records)
            if signature in self._emitted_signatures:
                continue
            self._emitted_signatures.add(signature)
            results.append([rec.payload for rec in records])

        return results

    def assert_facts(self, facts: Iterable[Dict[str, Any]]) -> List[List[Dict[str, Any]]]:
        """Convenience helper for asserting a batch of facts in order."""
        matches: List[List[Dict[str, Any]]] = []
        for fact in facts:
            matches.extend(self.assert_fact(fact))
        return matches

    def _store_fact(self, fact: Dict[str, Any]) -> _FactRecord:
        inserted_at = self._normalize_inserted_at(fact.get("inserted_at"))
        record = _FactRecord(fact_id=self._next_fact_id, payload=fact, inserted_at=inserted_at)
        self._next_fact_id += 1

        insert_at = bisect_right(self._fact_times, inserted_at)
        self._fact_times.insert(insert_at, inserted_at)
        self._facts_sorted.insert(insert_at, record)
        return record

    def _find_completions_ending_at(self, terminal: _FactRecord) -> List[List[_FactRecord]]:
        correlation = self._correlation_signature(terminal.payload)
        start_idx = self._facts_sorted.index(terminal)
        return self._match_prefix(
            step_idx=len(self.steps) - 2,
            max_idx=start_idx - 1,
            terminal=terminal,
            correlation=correlation,
        )

    def _match_prefix(
        self,
        *,
        step_idx: int,
        max_idx: int,
        terminal: _FactRecord,
        correlation: Tuple[Any, ...] | None,
    ) -> List[List[_FactRecord]]:
        if step_idx < 0:
            return [[terminal]]

        matches: List[List[_FactRecord]] = []
        for i in range(max_idx, -1, -1):
            candidate = self._facts_sorted[i]

            if not self._matches_step(candidate.payload, self.steps[step_idx]):
                continue

            if correlation is not None and self._correlation_signature(candidate.payload) != correlation:
                continue

            if self.within_window_seconds is not None:
                age_seconds = (terminal.inserted_at - candidate.inserted_at).total_seconds()
                if age_seconds > self.within_window_seconds:
                    # Earlier facts will only be older due to sort order.
                    break

            for tail in self._match_prefix(
                step_idx=step_idx - 1,
                max_idx=i - 1,
                terminal=terminal,
                correlation=correlation,
            ):
                matches.append([candidate, *tail])

        return matches

    def _matches_step(self, fact: Dict[str, Any], step: Dict[str, Any]) -> bool:
        field = step.get("field")
        op = step.get("op")
        expected = step.get("value")

        if field is None or op is None:
            return False

        return evaluate_operator(
            op,
            fact.get(field),
            expected,
            field_present=field in fact,
            strict_null_handling=settings.STRICT_NULL_HANDLING,
            strict_type_comparison=settings.STRICT_TYPE_COMPARISON,
            boolean_string_coercion=settings.BOOLEAN_STRING_COERCION,
        )

    def _correlation_signature(self, fact: Dict[str, Any]) -> Tuple[Any, ...] | None:
        if not self.correlate_on:
            return None
        return tuple(fact.get(field) for field in self.correlate_on)

    def _normalize_inserted_at(self, inserted_at: Any) -> datetime:
        if isinstance(inserted_at, datetime):
            if inserted_at.tzinfo is None:
                return inserted_at.replace(tzinfo=timezone.utc)
            return inserted_at

        if isinstance(inserted_at, (int, float)):
            return datetime.fromtimestamp(inserted_at, tz=timezone.utc)

        if isinstance(inserted_at, str):
            normalized = inserted_at.replace("Z", "+00:00")
            parsed = datetime.fromisoformat(normalized)
            if parsed.tzinfo is None:
                return parsed.replace(tzinfo=timezone.utc)
            return parsed

        raise ValueError("fact must include inserted_at as datetime, epoch seconds, or ISO8601 string")
