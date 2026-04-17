from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict


@dataclass
class FactRecord:
    fact_id: str
    payload: Dict[str, Any]
    revision: int = 0
    inserted_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class WorkingMemory:
    def __init__(self):
        self._facts: Dict[str, FactRecord] = {}
        self._clock = 0

    def insert_fact(self, fact_id: str, payload: Dict[str, Any]) -> FactRecord:
        self._clock += 1
        record = FactRecord(fact_id=fact_id, payload=dict(payload), revision=self._clock)
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
