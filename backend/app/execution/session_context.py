from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict

from app.execution.session_storage import SessionStorageBackend, SessionRecord


@dataclass
class SessionContext:
    session_id: str
    _storage: SessionStorageBackend

    @classmethod
    def from_record(cls, record: SessionRecord, storage: SessionStorageBackend) -> "SessionContext":
        return cls(session_id=record.session_id, _storage=storage)

    def assert_fact(self, fact_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        record = self._storage.assert_fact(self.session_id, fact_id, payload)
        return record.facts[fact_id]

    def retract_fact(self, fact_id: str) -> bool:
        return self._storage.retract_fact(self.session_id, fact_id)

    def facts(self) -> Dict[str, Dict[str, Any]]:
        record = self._storage.get_session(self.session_id)
        if record is None:
            return {}
        return dict(record.facts)

    def to_dict(self) -> Dict[str, Any]:
        record = self._storage.get_session(self.session_id)
        if record is None:
            return {"session_id": self.session_id, "facts": {}, "metadata": {}}
        return {
            "session_id": record.session_id,
            "facts": dict(record.facts),
            "metadata": dict(record.metadata),
            "created_at": record.created_at,
            "updated_at": record.updated_at,
        }
