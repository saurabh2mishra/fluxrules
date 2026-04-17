from __future__ import annotations

import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Callable, Dict


class SessionStorageBackend(ABC):
    """Storage contract for execution sessions and their mutable state."""

    @abstractmethod
    def create_session(self, session_id: str, ttl_seconds: int | None = None) -> bool:
        """Create a session if it does not exist. Returns True when created."""

    @abstractmethod
    def destroy_session(self, session_id: str) -> bool:
        """Destroy an existing session. Returns True when removed."""

    @abstractmethod
    def assert_fact(self, session_id: str, fact_id: str, payload: Dict[str, Any]) -> None:
        """Insert or replace a fact in the session's working set."""

    @abstractmethod
    def retract_fact(self, session_id: str, fact_id: str) -> bool:
        """Retract a fact from the session. Returns True when removed."""

    @abstractmethod
    def get_facts(self, session_id: str) -> Dict[str, Dict[str, Any]]:
        """Return all facts for a session keyed by fact id."""

    @abstractmethod
    def accumulate_counter(self, session_id: str, counter_key: str, delta: int = 1) -> int:
        """Apply a delta to a counter and return the resulting value."""

    @abstractmethod
    def next_sequence(
        self, session_id: str, sequence_key: str, *, start: int = 0, step: int = 1
    ) -> int:
        """Advance a named sequence and return the emitted value."""


@dataclass
class _SessionState:
    facts: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    counters: Dict[str, int] = field(default_factory=dict)
    sequences: Dict[str, int] = field(default_factory=dict)
    expires_at: float | None = None


class MemorySessionStorage(SessionStorageBackend):
    """In-memory development storage with lazy TTL expiration."""

    def __init__(
        self,
        default_ttl_seconds: int | None = 300,
        time_fn: Callable[[], float] | None = None,
    ):
        self._default_ttl_seconds = default_ttl_seconds
        self._time_fn = time_fn or time.time
        self._sessions: Dict[str, _SessionState] = {}

    def create_session(self, session_id: str, ttl_seconds: int | None = None) -> bool:
        self._purge_expired_sessions()
        if session_id in self._sessions:
            return False
        self._sessions[session_id] = _SessionState(expires_at=self._compute_expiry(ttl_seconds))
        return True

    def destroy_session(self, session_id: str) -> bool:
        self._purge_expired_sessions()
        return self._sessions.pop(session_id, None) is not None

    def assert_fact(self, session_id: str, fact_id: str, payload: Dict[str, Any]) -> None:
        state = self._get_session(session_id)
        state.facts[fact_id] = dict(payload)

    def retract_fact(self, session_id: str, fact_id: str) -> bool:
        state = self._get_session(session_id)
        return state.facts.pop(fact_id, None) is not None

    def get_facts(self, session_id: str) -> Dict[str, Dict[str, Any]]:
        state = self._get_session(session_id)
        return {fact_id: dict(payload) for fact_id, payload in state.facts.items()}

    def accumulate_counter(self, session_id: str, counter_key: str, delta: int = 1) -> int:
        state = self._get_session(session_id)
        value = state.counters.get(counter_key, 0) + delta
        state.counters[counter_key] = value
        return value

    def next_sequence(
        self, session_id: str, sequence_key: str, *, start: int = 0, step: int = 1
    ) -> int:
        state = self._get_session(session_id)
        if sequence_key not in state.sequences:
            state.sequences[sequence_key] = start
            return start

        next_value = state.sequences[sequence_key] + step
        state.sequences[sequence_key] = next_value
        return next_value

    def _compute_expiry(self, ttl_seconds: int | None) -> float | None:
        ttl = self._default_ttl_seconds if ttl_seconds is None else ttl_seconds
        if ttl is None:
            return None
        if ttl <= 0:
            return self._time_fn()
        return self._time_fn() + ttl

    def _touch_session(self, state: _SessionState) -> None:
        if state.expires_at is None:
            return
        if self._default_ttl_seconds is None:
            return
        state.expires_at = self._time_fn() + self._default_ttl_seconds

    def _get_session(self, session_id: str) -> _SessionState:
        self._purge_expired_sessions()
        state = self._sessions.get(session_id)
        if state is None:
            raise KeyError(f"Session '{session_id}' does not exist")
        self._touch_session(state)
        return state

    def _purge_expired_sessions(self) -> None:
        now = self._time_fn()
        expired = [
            session_id
            for session_id, state in self._sessions.items()
            if state.expires_at is not None and state.expires_at <= now
        ]
        for session_id in expired:
            self._sessions.pop(session_id, None)
