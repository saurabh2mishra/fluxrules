from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Iterable, List, Sequence, Tuple

from app.engine.comparison import evaluate_operator
from app.execution.working_memory import FactRecord, WorkingMemory


@dataclass(frozen=True)
class ActivationCandidate:
    """Minimal activation payload shape consumable by scheduler/session layers."""

    rule_id: str
    priority: int
    specificity: int
    matched_facts: List[Dict[str, Any]]
    context: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "rule_id": self.rule_id,
            "priority": self.priority,
            "specificity": self.specificity,
            "matched_facts": self.matched_facts,
            "context": self.context,
        }


class AccumulateEvaluator:
    """Evaluate basic accumulate clauses over working-memory facts.

    Supported behaviors:
      * filter via ``over``
      * optional ``window.duration_seconds`` using ``FactRecord.inserted_at``
      * optional grouping via ``group_by``
      * aggregate operators: count / sum / min / max / avg
      * optional post-aggregate ``constraint``
    """

    def evaluate(
        self,
        *,
        rule_id: str,
        priority: int,
        working_memory: WorkingMemory,
        accumulate: Dict[str, Any],
        now: datetime | None = None,
    ) -> List[Dict[str, Any]]:
        records = list(working_memory.facts().values())
        filtered_records = self._apply_filters(records, accumulate, now=now)
        grouped = self._group_records(filtered_records, accumulate.get("group_by"))

        candidates: List[ActivationCandidate] = []
        for group_key, rows in grouped:
            aggregates = self._compute_aggregates(rows, accumulate.get("aggregate"))
            group_context = self._group_context(accumulate.get("group_by"), group_key)
            context = {"group": group_context, "accumulate": aggregates}
            if not self._passes_constraint(context, accumulate.get("constraint")):
                continue
            candidates.append(
                ActivationCandidate(
                    rule_id=rule_id,
                    priority=priority,
                    specificity=len(rows),
                    matched_facts=[self._as_matched_fact(record) for record in rows],
                    context=context,
                )
            )

        return [candidate.to_dict() for candidate in candidates]

    def _apply_filters(
        self,
        records: Iterable[FactRecord],
        accumulate: Dict[str, Any],
        *,
        now: datetime | None,
    ) -> List[FactRecord]:
        over = accumulate.get("over")
        window = accumulate.get("window") or {}
        duration_seconds = window.get("duration_seconds")

        filtered: List[FactRecord] = []
        for record in records:
            if duration_seconds is not None and not self._in_window(record, duration_seconds, now=now):
                continue
            if not self._matches_over(record, over):
                continue
            filtered.append(record)
        return filtered

    @staticmethod
    def _in_window(record: FactRecord, duration_seconds: int, *, now: datetime | None) -> bool:
        if duration_seconds < 0:
            return False
        record_ts = record.inserted_at
        if now is None:
            if record_ts.tzinfo is None:
                now = datetime.now()
            else:
                now = datetime.now(timezone.utc)
        if record_ts.tzinfo is None and now.tzinfo is not None:
            now = now.replace(tzinfo=None)
        cutoff = now - timedelta(seconds=duration_seconds)
        return record_ts >= cutoff

    def _matches_over(self, record: FactRecord, over: Any) -> bool:
        if over in (None, "*"):
            return True

        payload = record.payload
        if isinstance(over, str):
            record_type = payload.get("type") or payload.get("fact_type")
            return record_type == over

        if isinstance(over, dict):
            # condition-style: {"field": "amount", "op": ">", "value": 100}
            if {"field", "op", "value"}.issubset(over.keys()):
                field = over["field"]
                return evaluate_operator(over["op"], payload.get(field), over["value"], field_present=field in payload)
            # equality-map style: {"type": "Order", "status": "approved"}
            return all(payload.get(field) == expected for field, expected in over.items())

        if isinstance(over, list):
            return all(self._matches_over(record, item) for item in over)

        return False

    @staticmethod
    def _group_records(records: Sequence[FactRecord], group_by: str | List[str] | None) -> List[Tuple[Tuple[Any, ...], List[FactRecord]]]:
        if not group_by:
            return [(tuple(), list(records))]

        fields = [group_by] if isinstance(group_by, str) else list(group_by)
        groups: Dict[Tuple[Any, ...], List[FactRecord]] = {}
        for record in records:
            key = tuple(record.payload.get(field) for field in fields)
            groups.setdefault(key, []).append(record)
        return list(groups.items())

    @staticmethod
    def _group_context(group_by: str | List[str] | None, key: Tuple[Any, ...]) -> Dict[str, Any]:
        if not group_by:
            return {}
        fields = [group_by] if isinstance(group_by, str) else list(group_by)
        return {field: key[idx] for idx, field in enumerate(fields)}

    def _compute_aggregates(self, records: Sequence[FactRecord], aggregate: Any) -> Dict[str, Any]:
        specs = self._normalize_aggregate_specs(aggregate)
        payloads = [record.payload for record in records]

        out: Dict[str, Any] = {}
        for spec in specs:
            op = spec["op"]
            field = spec.get("field")
            alias = spec.get("as") or self._default_alias(op, field)

            if op == "count":
                out[alias] = len(payloads)
                continue

            values = [payload.get(field) for payload in payloads if isinstance(payload.get(field), (int, float))]
            if op == "sum":
                out[alias] = float(sum(values)) if values else 0.0
            elif op == "min":
                out[alias] = min(values) if values else None
            elif op == "max":
                out[alias] = max(values) if values else None
            elif op == "avg":
                out[alias] = (float(sum(values)) / len(values)) if values else None
            else:
                raise ValueError(f"Unsupported aggregate op: {op}")
        return out

    @staticmethod
    def _normalize_aggregate_specs(aggregate: Any) -> List[Dict[str, Any]]:
        if aggregate is None:
            return [{"op": "count", "as": "count"}]
        if isinstance(aggregate, str):
            return [{"op": aggregate}]
        if isinstance(aggregate, dict):
            return [aggregate]
        if isinstance(aggregate, list):
            return list(aggregate)
        raise ValueError("Invalid aggregate definition")

    @staticmethod
    def _default_alias(op: str, field: str | None) -> str:
        if op == "count":
            return "count"
        if field:
            return f"{op}_{field}"
        return op

    def _passes_constraint(self, context: Dict[str, Any], constraint: Dict[str, Any] | None) -> bool:
        if not constraint:
            return True

        field = constraint["field"]
        op = constraint["op"]
        value = constraint["value"]
        actual = self._resolve_context_field(context, field)
        return evaluate_operator(op, actual, value, field_present=actual is not None)

    @staticmethod
    def _resolve_context_field(context: Dict[str, Any], field: str) -> Any:
        if "." not in field:
            if field in context:
                return context[field]
            return context.get("accumulate", {}).get(field)

        current: Any = context
        for part in field.split("."):
            if not isinstance(current, dict):
                return None
            current = current.get(part)
        return current

    @staticmethod
    def _as_matched_fact(record: FactRecord) -> Dict[str, Any]:
        return {
            "fact_id": record.fact_id,
            "payload": dict(record.payload),
            "revision": record.revision,
            "inserted_at": record.inserted_at.isoformat(),
        }
