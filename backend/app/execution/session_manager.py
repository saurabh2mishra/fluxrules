from __future__ import annotations

import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

from app.config import settings
from app.execution.session_storage import SessionStorageBackend, get_session_storage
from app.execution.working_memory import FactRecord, WorkingMemory

SESSION_MAX_CONCURRENT = int(getattr(settings, "SESSION_MAX_CONCURRENT", 100))
SESSION_CLEANUP_INTERVAL_SECONDS = 1.0


@dataclass
class SessionContext:
    session_id: str
    group: str
    ttl: float
    db: Any
    working_memory: WorkingMemory = field(default_factory=WorkingMemory)
    expires_at: float = 0.0

    def refresh_expiry(self) -> None:
        self.expires_at = time.time() + self.ttl


class SessionManager:
    """
    Dual-mode session manager.

    - Legacy mode (default): in-memory contexts with TTL/locks used by engine tests.
    - Backend mode (when `backend=` provided): CRUD facade over SessionStorageBackend
      used by API/storage integration tests.
    """

    def __init__(
        self,
        cleanup_interval_seconds: float = SESSION_CLEANUP_INTERVAL_SECONDS,
        backend: Optional[SessionStorageBackend] = None,
    ):
        self._backend = backend

        # Legacy mode state
        self._sessions: Dict[str, SessionContext] = {}
        self._manager_lock = threading.Lock()
        self._session_locks: Dict[str, threading.Lock] = {}
        self._max_concurrent = int(SESSION_MAX_CONCURRENT)
        self._cleanup_interval_seconds = cleanup_interval_seconds
        self._stop_cleanup = threading.Event()
        self._cleanup_thread: threading.Thread | None = None

        if self._backend is None:
            self._cleanup_thread = threading.Thread(target=self._cleanup_loop, daemon=True)
            self._cleanup_thread.start()

    def create_session(self, *args: Any, **kwargs: Any) -> Any:
        if self._backend is not None:
            session_id = kwargs.get("session_id")
            metadata = kwargs.get("metadata")
            if session_id is None and args:
                session_id = args[0]
            if metadata is None and len(args) > 1:
                metadata = args[1]
            if session_id is None:
                raise TypeError("session_id is required")
            return self._backend.create_session(session_id=session_id, metadata=metadata)

        group = kwargs.get("group")
        ttl = kwargs.get("ttl")
        db = kwargs.get("db")
        if group is None and args:
            group = args[0]
        if ttl is None and len(args) > 1:
            ttl = args[1]
        if db is None and len(args) > 2:
            db = args[2]
        if group is None or ttl is None:
            raise TypeError("group and ttl are required in legacy mode")

        with self._manager_lock:
            self._cleanup_expired_sessions_locked()
            if len(self._sessions) >= self._max_concurrent:
                raise RuntimeError("SESSION_MAX_CONCURRENT exceeded")

            session_id = str(uuid.uuid4())
            context = SessionContext(session_id=session_id, group=group, ttl=float(ttl), db=db)
            context.refresh_expiry()
            self._sessions[session_id] = context
            self._session_locks[session_id] = threading.Lock()
            return context

    def get_session(self, session_id: str) -> Any:
        if self._backend is not None:
            return self._backend.get_session(session_id)

        with self._manager_lock:
            session = self._sessions.get(session_id)
            if session is None:
                return None
            if session.expires_at <= time.time():
                self._destroy_session_locked(session_id)
                return None
            return session

    def list_sessions(self) -> Any:
        if self._backend is None:
            with self._manager_lock:
                self._cleanup_expired_sessions_locked()
                return list(self._sessions.values())
        return list(self._backend.list_sessions())

    def assert_fact(self, session_id: str, fact_id: str, event: Any) -> Any:
        if self._backend is not None:
            payload = getattr(event, "data", event)
            if not isinstance(payload, dict):
                raise TypeError("event must expose a dict payload via .data or be a dict")
            return self._backend.assert_fact(session_id, fact_id, payload)

        event_data = getattr(event, "data", event)
        if not isinstance(event_data, dict):
            raise TypeError("event must expose a dict payload via .data or be a dict")

        lock: threading.Lock
        with self._manager_lock:
            context = self._sessions.get(session_id)
            lock = self._session_locks.get(session_id)
            if context is None or lock is None:
                raise KeyError(f"Session not found: {session_id}")
            if context.expires_at <= time.time():
                self._destroy_session_locked(session_id)
                raise KeyError(f"Session not found: {session_id}")

            lock.acquire()

        try:
            record = context.working_memory.update_fact(fact_id, event_data)
            context.refresh_expiry()
            return record
        finally:
            lock.release()

    def retract_fact(self, session_id: str, fact_id: str) -> bool:
        if self._backend is not None:
            return self._backend.retract_fact(session_id, fact_id)

        with self._manager_lock:
            context = self._sessions.get(session_id)
            if context is None:
                return False
            lock = self._session_locks.get(session_id)
            if lock is None:
                return False
            lock.acquire()
        try:
            deleted = context.working_memory.retract_fact(fact_id)
            if deleted:
                context.refresh_expiry()
            return deleted
        finally:
            lock.release()

    def delete_session(self, session_id: str) -> bool:
        if self._backend is not None:
            return self._backend.delete_session(session_id)
        return self.destroy_session(session_id)

    def destroy_session(self, session_id: str) -> bool:
        if self._backend is not None:
            return self._backend.delete_session(session_id)
        with self._manager_lock:
            return self._destroy_session_locked(session_id)

    def cleanup_expired_sessions(self) -> int:
        if self._backend is not None:
            return 0
        with self._manager_lock:
            return self._cleanup_expired_sessions_locked()

    def close(self) -> None:
        if self._cleanup_thread is None:
            return
        self._stop_cleanup.set()
        self._cleanup_thread.join(timeout=1.0)

    def _cleanup_loop(self) -> None:
        while not self._stop_cleanup.is_set():
            self._stop_cleanup.wait(self._cleanup_interval_seconds)
            if self._stop_cleanup.is_set():
                break
            self.cleanup_expired_sessions()

    def _cleanup_expired_sessions_locked(self) -> int:
        now = time.time()
        expired = [
            session_id
            for session_id, session in self._sessions.items()
            if session.expires_at <= now
        ]
        for session_id in expired:
            self._destroy_session_locked(session_id)
        return len(expired)

    def _destroy_session_locked(self, session_id: str) -> bool:
        lock = self._session_locks.get(session_id)
        if lock is not None:
            lock.acquire()
        removed = self._sessions.pop(session_id, None)
        self._session_locks.pop(session_id, None)
        if lock is not None:
            lock.release()
        return removed is not None


_manager_singleton: SessionManager | None = None


def get_session_manager() -> SessionManager:
    global _manager_singleton
    if _manager_singleton is None:
        _manager_singleton = SessionManager(backend=get_session_storage())
    return _manager_singleton
