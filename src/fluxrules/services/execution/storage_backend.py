"""Storage backends for execution sessions"""

from __future__ import annotations

import json
import logging
import time
from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any


def _get_redis_client():
    """Lazy optional redis import - returns None if redis is not installed."""
    try:
        import redis as _redis_mod
    except ImportError:
        return None
    try:
        from fluxrules.engine.configuration import get_config

        cfg = get_config()
        host = getattr(cfg, "redis_host", "localhost")
        port = getattr(cfg, "redis_port", 6379)
        db = getattr(cfg, "redis_db", 0)
        client = _redis_mod.Redis(host=host, port=port, db=db, decode_responses=False)
        client.ping()
        return client
    except Exception:
        return None


logger = logging.getLogger(__name__)


#  Settings shim - tests monkeypatch ``storage_backend.settings``
class _Settings:
    """Minimal settings object for standalone / test usage."""

    def __init__(self):
        import os

        self.FLUXRULES_ENV = os.environ.get("FLUXRULES_ENV", "development").lower()


settings = _Settings()


# Public alias so tests can monkeypatch ``storage_backend.get_redis_client``
get_redis_client = _get_redis_client


class SessionStorageBackend(ABC):
    """Storage contract for execution sessions and their mutable state."""

    @abstractmethod
    def create_session(self, session_id: str, ttl_seconds: int | None = None) -> bool:
        """Create a session if it does not exist. Returns True when created."""

    @abstractmethod
    def destroy_session(self, session_id: str) -> bool:
        """Destroy an existing session. Returns True when removed."""

    @abstractmethod
    def assert_fact(self, session_id: str, fact_id: str, payload: dict[str, Any]) -> None:
        """Insert or replace a fact in the session's working set."""

    @abstractmethod
    def retract_fact(self, session_id: str, fact_id: str) -> bool:
        """Retract a fact from the session. Returns True when removed."""

    @abstractmethod
    def get_facts(self, session_id: str) -> dict[str, dict[str, Any]]:
        """Return all facts for a session keyed by fact id."""

    @abstractmethod
    def accumulate_counter(self, session_id: str, counter_key: str, delta: int = 1) -> int:
        """Apply a delta to a counter and return the resulting value."""

    @abstractmethod
    def next_sequence(
        self, session_id: str, sequence_key: str, *, start: int = 0, step: int = 1
    ) -> int:
        """Advance a named sequence and return the emitted value."""


# Keep the old name as an alias for any code that already imported StorageBackend
StorageBackend = SessionStorageBackend


@dataclass
class _SessionState:
    facts: dict[str, dict[str, Any]] = field(default_factory=dict)
    counters: dict[str, int] = field(default_factory=dict)
    sequences: dict[str, int] = field(default_factory=dict)
    metadata: dict[str, dict[str, Any]] = field(default_factory=dict)
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
        self._sessions: dict[str, _SessionState] = {}

    def create_session(self, session_id: str, ttl_seconds: int | None = None) -> bool:
        self._purge_expired_sessions()
        if session_id in self._sessions:
            return False
        self._sessions[session_id] = _SessionState(expires_at=self._compute_expiry(ttl_seconds))
        return True

    def destroy_session(self, session_id: str) -> bool:
        self._purge_expired_sessions()
        return self._sessions.pop(session_id, None) is not None

    def assert_fact(self, session_id: str, fact_id: str, payload: dict[str, Any]) -> None:
        state = self._get_session(session_id)
        state.facts[fact_id] = dict(payload)

    def retract_fact(self, session_id: str, fact_id: str) -> bool:
        state = self._get_session(session_id)
        return state.facts.pop(fact_id, None) is not None

    def get_facts(self, session_id: str) -> dict[str, dict[str, Any]]:
        state = self._get_session(session_id)
        return {fid: dict(p) for fid, p in state.facts.items()}

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
        nv = state.sequences[sequence_key] + step
        state.sequences[sequence_key] = nv
        return nv

    # Convenience helpers used by the session store.
    def set_fact(self, session_id: str, fact_id: str, payload: dict[str, Any]) -> None:
        self.create_session(session_id)
        self.assert_fact(session_id, fact_id, payload)

    def get_fact(self, session_id: str, fact_id: str) -> dict[str, Any] | None:
        return self.get_facts(session_id).get(fact_id)

    def list_facts(self, session_id: str) -> dict[str, dict[str, Any]]:
        return self.get_facts(session_id)

    def delete_fact(self, session_id: str, fact_id: str) -> bool:
        return self.retract_fact(session_id, fact_id)

    def increment_counter(self, session_id: str, counter_key: str, delta: int = 1) -> int:
        return self.accumulate_counter(session_id, counter_key, delta)

    def set_metadata(self, session_id: str, key: str, payload: dict[str, Any]) -> None:
        self.create_session(session_id)
        state = self._get_session(session_id)
        state.metadata[key] = dict(payload)

    def get_metadata(self, session_id: str, key: str) -> dict[str, Any] | None:
        try:
            state = self._get_session(session_id)
        except KeyError:
            return None
        v = state.metadata.get(key)
        return dict(v) if v is not None else None

    def _compute_expiry(self, ttl_seconds: int | None) -> float | None:
        ttl = self._default_ttl_seconds if ttl_seconds is None else ttl_seconds
        if ttl is None:
            return None
        if ttl <= 0:
            return self._time_fn()
        return self._time_fn() + ttl

    def _touch_session(self, state: _SessionState) -> None:
        if state.expires_at is None or self._default_ttl_seconds is None:
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
            sid
            for sid, st in self._sessions.items()
            if st.expires_at is not None and st.expires_at <= now
        ]
        for sid in expired:
            self._sessions.pop(sid, None)


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
        for key in (
            self._facts_key(sid),
            self._counter_key(sid),
            self._sequence_key(sid),
            self._metadata_key(sid),
        ):
            self._redis.expire(key, self._ttl_seconds)

    def set_fact(self, sid: str, fact_id: str, payload: dict[str, Any]) -> None:
        self._redis.hset(self._facts_key(sid), fact_id, json.dumps(payload))
        self._touch_ttl(sid)

    def get_fact(self, sid: str, fact_id: str) -> dict[str, Any] | None:
        raw = self._redis.hget(self._facts_key(sid), fact_id)
        if raw is None:
            return None
        return json.loads(raw.decode("utf-8") if isinstance(raw, bytes) else raw)

    def list_facts(self, sid: str) -> dict[str, dict[str, Any]]:
        values = self._redis.hgetall(self._facts_key(sid))
        return {
            (k.decode("utf-8") if isinstance(k, bytes) else k): json.loads(
                v.decode("utf-8") if isinstance(v, bytes) else v
            )
            for k, v in values.items()
        }

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

    def set_metadata(self, sid: str, key: str, payload: dict[str, Any]) -> None:
        self._redis.hset(self._metadata_key(sid), key, json.dumps(payload))
        self._touch_ttl(sid)

    def get_metadata(self, sid: str, key: str) -> dict[str, Any] | None:
        raw = self._redis.hget(self._metadata_key(sid), key)
        if raw is None:
            return None
        return json.loads(raw.decode("utf-8") if isinstance(raw, bytes) else raw)


# Aliases for the in-memory session storage.
InMemorySessionStorage = MemorySessionStorage
MemoryStorageBackend = MemorySessionStorage  # alias used by unit tests


def get_session_storage() -> Any:
    redis_client = get_redis_client()
    if redis_client is not None:
        return RedisSessionStorage(redis_client=redis_client)

    env = getattr(settings, "FLUXRULES_ENV", "development").lower()
    if env == "production":
        raise RuntimeError("Redis is required in production")

    logger.warning("Redis unavailable; using in-memory session storage fallback")
    return InMemorySessionStorage()
