from __future__ import annotations

import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict

from app.config import settings
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
    def __init__(self, cleanup_interval_seconds: float = SESSION_CLEANUP_INTERVAL_SECONDS):
        self._sessions: Dict[str, SessionContext] = {}
        self._manager_lock = threading.Lock()
        self._session_locks: Dict[str, threading.Lock] = {}

        self._max_concurrent = int(SESSION_MAX_CONCURRENT)
        self._cleanup_interval_seconds = cleanup_interval_seconds
        self._stop_cleanup = threading.Event()
        self._cleanup_thread = threading.Thread(target=self._cleanup_loop, daemon=True)
        self._cleanup_thread.start()

    def create_session(self, group: str, ttl: float, db: Any) -> SessionContext:
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

    def get_session(self, session_id: str) -> SessionContext | None:
        with self._manager_lock:
            session = self._sessions.get(session_id)
            if session is None:
                return None
            if session.expires_at <= time.time():
                self._destroy_session_locked(session_id)
                return None
            return session

    def assert_fact(self, session_id: str, fact_id: str, event: Any) -> FactRecord:
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

    def destroy_session(self, session_id: str) -> bool:
        with self._manager_lock:
            return self._destroy_session_locked(session_id)

    def cleanup_expired_sessions(self) -> int:
        with self._manager_lock:
            return self._cleanup_expired_sessions_locked()

    def close(self) -> None:
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
