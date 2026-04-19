from __future__ import annotations

import json
import threading
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, Optional

from app.config import settings
from app.utils.redis_client import get_redis_client


@dataclass
class SessionRecord:
    session_id: str
    facts: Dict[str, Dict[str, Any]]
    metadata: Dict[str, Any]
    created_at: str
    updated_at: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "session_id": self.session_id,
            "facts": dict(self.facts),
            "metadata": dict(self.metadata),
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


class SessionStorageBackend(ABC):
    @abstractmethod
    def create_session(self, session_id: str, metadata: Optional[Dict[str, Any]] = None) -> SessionRecord:
        raise NotImplementedError

    @abstractmethod
    def get_session(self, session_id: str) -> Optional[SessionRecord]:
        raise NotImplementedError

    @abstractmethod
    def list_sessions(self) -> Iterable[SessionRecord]:
        raise NotImplementedError

    @abstractmethod
    def delete_session(self, session_id: str) -> bool:
        raise NotImplementedError

    @abstractmethod
    def assert_fact(self, session_id: str, fact_id: str, payload: Dict[str, Any]) -> SessionRecord:
        raise NotImplementedError

    @abstractmethod
    def retract_fact(self, session_id: str, fact_id: str) -> bool:
        raise NotImplementedError


class MemorySessionStorageBackend(SessionStorageBackend):
    def __init__(self) -> None:
        self._sessions: Dict[str, SessionRecord] = {}
        self._lock = threading.RLock()

    def _now(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def create_session(self, session_id: str, metadata: Optional[Dict[str, Any]] = None) -> SessionRecord:
        with self._lock:
            now = self._now()
            record = SessionRecord(
                session_id=session_id,
                facts={},
                metadata=dict(metadata or {}),
                created_at=now,
                updated_at=now,
            )
            self._sessions[session_id] = record
            return record

    def get_session(self, session_id: str) -> Optional[SessionRecord]:
        with self._lock:
            record = self._sessions.get(session_id)
            if record is None:
                return None
            return SessionRecord(
                session_id=record.session_id,
                facts=dict(record.facts),
                metadata=dict(record.metadata),
                created_at=record.created_at,
                updated_at=record.updated_at,
            )

    def list_sessions(self) -> Iterable[SessionRecord]:
        with self._lock:
            return [
                SessionRecord(
                    session_id=record.session_id,
                    facts=dict(record.facts),
                    metadata=dict(record.metadata),
                    created_at=record.created_at,
                    updated_at=record.updated_at,
                )
                for record in self._sessions.values()
            ]

    def delete_session(self, session_id: str) -> bool:
        with self._lock:
            return self._sessions.pop(session_id, None) is not None

    def assert_fact(self, session_id: str, fact_id: str, payload: Dict[str, Any]) -> SessionRecord:
        with self._lock:
            record = self._sessions.get(session_id)
            if record is None:
                record = self.create_session(session_id)
            record.facts[fact_id] = dict(payload)
            record.updated_at = self._now()
            return SessionRecord(
                session_id=record.session_id,
                facts=dict(record.facts),
                metadata=dict(record.metadata),
                created_at=record.created_at,
                updated_at=record.updated_at,
            )

    def retract_fact(self, session_id: str, fact_id: str) -> bool:
        with self._lock:
            record = self._sessions.get(session_id)
            if record is None:
                return False
            deleted = record.facts.pop(fact_id, None) is not None
            if deleted:
                record.updated_at = self._now()
            return deleted


class RedisSessionStorageBackend(SessionStorageBackend):
    def __init__(self, redis_client: Any, prefix: str = "session_ctx") -> None:
        self._redis = redis_client
        self._prefix = prefix

    def _key(self, session_id: str) -> str:
        return f"{self._prefix}:{session_id}"

    def _now(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def _decode(self, raw: Any) -> Optional[SessionRecord]:
        if raw is None:
            return None
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8")
        data = json.loads(raw)
        return SessionRecord(
            session_id=data["session_id"],
            facts=data.get("facts", {}),
            metadata=data.get("metadata", {}),
            created_at=data["created_at"],
            updated_at=data["updated_at"],
        )

    def _encode(self, record: SessionRecord) -> str:
        return json.dumps(
            {
                "session_id": record.session_id,
                "facts": record.facts,
                "metadata": record.metadata,
                "created_at": record.created_at,
                "updated_at": record.updated_at,
            }
        )

    def create_session(self, session_id: str, metadata: Optional[Dict[str, Any]] = None) -> SessionRecord:
        now = self._now()
        record = SessionRecord(
            session_id=session_id,
            facts={},
            metadata=dict(metadata or {}),
            created_at=now,
            updated_at=now,
        )
        self._redis.set(self._key(session_id), self._encode(record))
        return record

    def get_session(self, session_id: str) -> Optional[SessionRecord]:
        return self._decode(self._redis.get(self._key(session_id)))

    def list_sessions(self) -> Iterable[SessionRecord]:
        records = []
        for key in self._redis.scan_iter(f"{self._prefix}:*"):
            if isinstance(key, bytes):
                key = key.decode("utf-8")
            raw = self._redis.get(key)
            record = self._decode(raw)
            if record is not None:
                records.append(record)
        return records

    def delete_session(self, session_id: str) -> bool:
        return bool(self._redis.delete(self._key(session_id)))

    def assert_fact(self, session_id: str, fact_id: str, payload: Dict[str, Any]) -> SessionRecord:
        record = self.get_session(session_id)
        if record is None:
            record = self.create_session(session_id)
        record.facts[fact_id] = dict(payload)
        record.updated_at = self._now()
        self._redis.set(self._key(session_id), self._encode(record))
        return record

    def retract_fact(self, session_id: str, fact_id: str) -> bool:
        record = self.get_session(session_id)
        if record is None:
            return False
        deleted = record.facts.pop(fact_id, None) is not None
        if deleted:
            record.updated_at = self._now()
            self._redis.set(self._key(session_id), self._encode(record))
        return deleted


_storage_singleton: Optional[SessionStorageBackend] = None


def get_session_storage() -> SessionStorageBackend:
    global _storage_singleton
    if _storage_singleton is not None:
        return _storage_singleton

    backend_name = getattr(settings, "SESSION_STORAGE_BACKEND", "memory").lower()
    if backend_name == "redis":
        redis_client = get_redis_client()
        if redis_client is not None:
            _storage_singleton = RedisSessionStorageBackend(
                redis_client=redis_client,
                prefix=getattr(settings, "SESSION_STORAGE_PREFIX", "session_ctx"),
            )
            return _storage_singleton

    _storage_singleton = MemorySessionStorageBackend()
    return _storage_singleton
