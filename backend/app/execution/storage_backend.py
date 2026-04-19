from __future__ import annotations

import json
import logging
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Callable, Dict

from app.config import settings
from app.utils.redis_client import get_redis_client

logger = logging.getLogger(__name__)


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

    # Backward-compatible helper names used by legacy tests.
    def set_fact(self, session_id: str, fact_id: str, payload: Dict[str, Any]) -> None:
        self.create_session(session_id)
        self.assert_fact(session_id, fact_id, payload)

    def get_fact(self, session_id: str, fact_id: str) -> Dict[str, Any] | None:
        return self.get_facts(session_id).get(fact_id)

    def list_facts(self, session_id: str) -> Dict[str, Dict[str, Any]]:
        return self.get_facts(session_id)

    def delete_fact(self, session_id: str, fact_id: str) -> bool:
        return self.retract_fact(session_id, fact_id)

    def increment_counter(self, session_id: str, counter_key: str, delta: int = 1) -> int:
        return self.accumulate_counter(session_id, counter_key, delta)

    def set_metadata(self, session_id: str, key: str, payload: Dict[str, Any]) -> None:
        self.create_session(session_id)

    def get_metadata(self, session_id: str, key: str) -> Dict[str, Any] | None:
        return None

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


class RedisSessionStorage:
    def __init__(self, redis_client: Any, ttl_seconds: int = 300, prefix: str = "session"):
        self._redis = redis_client
        self._ttl_seconds = ttl_seconds
        self._prefix = prefix

    def _facts_key(self, sid: str) -> str:
        return f"{self._prefix}:{sid}:facts"

    def _counter_key(self, sid: str) -> str:
        return f"{self._prefix}:{sid}:counters"

    def _sequence_key(self, sid: str) -> str:
        return f"{self._prefix}:{sid}:sequences"

    def _metadata_key(self, sid: str) -> str:
        return f"{self._prefix}:{sid}:metadata"

    def _touch_ttl(self, sid: str) -> None:
        for key in (self._facts_key(sid), self._counter_key(sid), self._sequence_key(sid), self._metadata_key(sid)):
            self._redis.expire(key, self._ttl_seconds)

    def set_fact(self, sid: str, fact_id: str, payload: Dict[str, Any]) -> None:
        self._redis.hset(self._facts_key(sid), fact_id, json.dumps(payload))
        self._touch_ttl(sid)

    def get_fact(self, sid: str, fact_id: str) -> Dict[str, Any] | None:
        raw = self._redis.hget(self._facts_key(sid), fact_id)
        if raw is None:
            return None
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8")
        return json.loads(raw)

    def list_facts(self, sid: str) -> Dict[str, Dict[str, Any]]:
        values = self._redis.hgetall(self._facts_key(sid))
        decoded: Dict[str, Dict[str, Any]] = {}
        for key, raw in values.items():
            k = key.decode("utf-8") if isinstance(key, bytes) else key
            rv = raw.decode("utf-8") if isinstance(raw, bytes) else raw
            decoded[k] = json.loads(rv)
        return decoded

    def delete_fact(self, sid: str, fact_id: str) -> bool:
        removed = bool(self._redis.hdel(self._facts_key(sid), fact_id))
        self._touch_ttl(sid)
        return removed

    def increment_counter(self, sid: str, counter_key: str, delta: int = 1) -> int:
        value = self._redis.zincrby(self._counter_key(sid), delta, counter_key)
        self._touch_ttl(sid)
        return int(value)

    def next_sequence(self, sid: str, sequence_key: str) -> int:
        value = self._redis.zincrby(self._sequence_key(sid), 1, sequence_key)
        self._touch_ttl(sid)
        return int(value)

    def set_metadata(self, sid: str, key: str, payload: Dict[str, Any]) -> None:
        self._redis.hset(self._metadata_key(sid), key, json.dumps(payload))
        self._touch_ttl(sid)

    def get_metadata(self, sid: str, key: str) -> Dict[str, Any] | None:
        raw = self._redis.hget(self._metadata_key(sid), key)
        if raw is None:
            return None
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8")
        return json.loads(raw)


# Backward-compatible symbol expected by tests.
InMemorySessionStorage = MemorySessionStorage


def get_session_storage() -> Any:
    redis_client = get_redis_client()
    if redis_client is not None:
        return RedisSessionStorage(redis_client=redis_client)

    env = getattr(settings, "FLUXRULES_ENV", "development").lower()
    if env == "production":
        raise RuntimeError("Redis is required in production")

    logger.warning("Redis unavailable; using in-memory session storage fallback")
    return InMemorySessionStorage()
