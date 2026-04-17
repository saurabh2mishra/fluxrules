from __future__ import annotations

import uuid
from typing import Any, Dict, List, Optional

from app.execution.session_context import SessionContext
from app.execution.session_storage import SessionStorageBackend, get_session_storage


class SessionManager:
    def __init__(self, backend: Optional[SessionStorageBackend] = None) -> None:
        self._storage = backend or get_session_storage()

    def create_session(self, session_id: Optional[str] = None, metadata: Optional[Dict[str, Any]] = None) -> SessionContext:
        resolved_id = session_id or str(uuid.uuid4())
        record = self._storage.create_session(resolved_id, metadata=metadata)
        return SessionContext.from_record(record, self._storage)

    def get_session(self, session_id: str) -> Optional[SessionContext]:
        record = self._storage.get_session(session_id)
        if record is None:
            return None
        return SessionContext.from_record(record, self._storage)

    def list_sessions(self) -> List[SessionContext]:
        return [SessionContext.from_record(record, self._storage) for record in self._storage.list_sessions()]

    def delete_session(self, session_id: str) -> bool:
        return self._storage.delete_session(session_id)

    def assert_fact(self, session_id: str, fact_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        record = self._storage.assert_fact(session_id, fact_id, payload)
        return record.facts[fact_id]

    def retract_fact(self, session_id: str, fact_id: str) -> bool:
        return self._storage.retract_fact(session_id, fact_id)

    def get_facts(self, session_id: str) -> Dict[str, Dict[str, Any]]:
        record = self._storage.get_session(session_id)
        if record is None:
            return {}
        return dict(record.facts)


def get_session_manager() -> SessionManager:
    return SessionManager()
