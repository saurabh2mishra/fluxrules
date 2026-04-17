from __future__ import annotations

import sys
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Set


@dataclass
class FactRecord:
    fact_id: str
    payload: Dict[str, Any]
    revision: int = 0
    inserted_at: float = 0.0


class WorkingMemory:
    def __init__(self, max_facts: int = 1000):
        if max_facts <= 0:
            raise ValueError("max_facts must be greater than zero")
        self._facts: Dict[str, FactRecord] = {}
        self._clock = 0
        self._max_facts = max_facts
        self._last_evicted: Optional[FactRecord] = None

    def insert_fact(self, fact_id: str, payload: Dict[str, Any]) -> FactRecord:
        self._last_evicted = None
        if fact_id not in self._facts and len(self._facts) >= self._max_facts:
            oldest_fact_id = next(iter(self._facts))
            self._last_evicted = self._facts.pop(oldest_fact_id)

        self._clock += 1
        record = FactRecord(
            fact_id=fact_id,
            payload=dict(payload),
            revision=self._clock,
            inserted_at=time.time(),
        )
        self._facts[fact_id] = record
        return record

    def update_fact(self, fact_id: str, payload: Dict[str, Any]) -> FactRecord:
        if fact_id not in self._facts:
            return self.insert_fact(fact_id, payload)
        self._clock += 1
        record = self._facts[fact_id]
        record.payload = dict(payload)
        record.revision = self._clock
        return record

    def retract_fact(self, fact_id: str) -> bool:
        return self._facts.pop(fact_id, None) is not None

    def facts(self) -> Dict[str, FactRecord]:
        return self._facts

    def get_facts_in_window(self, seconds: int) -> List[FactRecord]:
        now = time.time()
        lower_bound = now - max(0, seconds)
        return [record for record in self._facts.values() if record.inserted_at >= lower_bound]

    def get_facts_by_field(self, field: str, value: Any) -> List[FactRecord]:
        return [record for record in self._facts.values() if record.payload.get(field) == value]

    def memory_estimate(self) -> int:
        seen: Set[int] = set()
        return self._deep_size(self._facts, seen)

    @property
    def last_evicted(self) -> Optional[FactRecord]:
        return self._last_evicted

    @staticmethod
    def _deep_size(obj: Any, seen: Set[int]) -> int:
        obj_id = id(obj)
        if obj_id in seen:
            return 0
        seen.add(obj_id)

        size = sys.getsizeof(obj)
        if isinstance(obj, dict):
            for key, value in obj.items():
                size += WorkingMemory._deep_size(key, seen)
                size += WorkingMemory._deep_size(value, seen)
        elif isinstance(obj, (list, tuple, set, frozenset)):
            for item in obj:
                size += WorkingMemory._deep_size(item, seen)
        elif isinstance(obj, FactRecord):
            size += WorkingMemory._deep_size(obj.fact_id, seen)
            size += WorkingMemory._deep_size(obj.payload, seen)
            size += WorkingMemory._deep_size(obj.revision, seen)
            size += WorkingMemory._deep_size(obj.inserted_at, seen)

        return size
