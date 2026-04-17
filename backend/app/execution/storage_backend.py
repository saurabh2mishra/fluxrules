from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from app.config import settings
from app.utils.redis_client import get_redis_client

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SessionStorageKeys:
    session_id: str

    @property
    def facts(self) -> str:
        return f"session:{self.session_id}:facts"

    @property
    def counters(self) -> str:
        return f"session:{self.session_id}:counters"

    @property
    def sequences(self) -> str:
        return f"session:{self.session_id}:sequences"

    @property
    def metadata(self) -> str:
        return f"session:{self.session_id}:metadata"


class SessionStorage:
    def set_fact(self, session_id: str, fact_id: str, payload: Dict[str, Any]) -> None:
        raise NotImplementedError

    def get_fact(self, session_id: str, fact_id: str) -> Optional[Dict[str, Any]]:
        raise NotImplementedError

    def delete_fact(self, session_id: str, fact_id: str) -> bool:
        raise NotImplementedError

    def list_facts(self, session_id: str) -> Dict[str, Dict[str, Any]]:
        raise NotImplementedError

    def increment_counter(self, session_id: str, name: str, delta: int = 1) -> int:
        raise NotImplementedError

    def next_sequence(self, session_id: str, name: str) -> int:
        raise NotImplementedError

    def set_metadata(self, session_id: str, key: str, value: Any) -> None:
        raise NotImplementedError

    def get_metadata(self, session_id: str, key: str) -> Any:
        raise NotImplementedError


class InMemorySessionStorage(SessionStorage):
    def __init__(self):
        self._facts: Dict[str, Dict[str, Dict[str, Any]]] = {}
        self._counters: Dict[str, Dict[str, int]] = {}
        self._sequences: Dict[str, Dict[str, int]] = {}
        self._metadata: Dict[str, Dict[str, Any]] = {}

    def set_fact(self, session_id: str, fact_id: str, payload: Dict[str, Any]) -> None:
        self._facts.setdefault(session_id, {})[fact_id] = dict(payload)

    def get_fact(self, session_id: str, fact_id: str) -> Optional[Dict[str, Any]]:
        fact = self._facts.get(session_id, {}).get(fact_id)
        return dict(fact) if fact is not None else None

    def delete_fact(self, session_id: str, fact_id: str) -> bool:
        return self._facts.get(session_id, {}).pop(fact_id, None) is not None

    def list_facts(self, session_id: str) -> Dict[str, Dict[str, Any]]:
        return {k: dict(v) for k, v in self._facts.get(session_id, {}).items()}

    def increment_counter(self, session_id: str, name: str, delta: int = 1) -> int:
        current = self._counters.setdefault(session_id, {}).get(name, 0) + delta
        self._counters[session_id][name] = current
        return current

    def next_sequence(self, session_id: str, name: str) -> int:
        return self.increment_counter(session_id, name=f"__seq__:{name}", delta=1)

    def set_metadata(self, session_id: str, key: str, value: Any) -> None:
        self._metadata.setdefault(session_id, {})[key] = value

    def get_metadata(self, session_id: str, key: str) -> Any:
        return self._metadata.get(session_id, {}).get(key)


class RedisSessionStorage(SessionStorage):
    def __init__(self, redis_client, ttl_seconds: int = 3600):
        self.redis = redis_client
        self.ttl_seconds = ttl_seconds

    def _keys(self, session_id: str) -> SessionStorageKeys:
        return SessionStorageKeys(session_id=session_id)

    def _expire_all(self, keys: SessionStorageKeys) -> None:
        self.redis.expire(keys.facts, self.ttl_seconds)
        self.redis.expire(keys.counters, self.ttl_seconds)
        self.redis.expire(keys.sequences, self.ttl_seconds)
        self.redis.expire(keys.metadata, self.ttl_seconds)

    def set_fact(self, session_id: str, fact_id: str, payload: Dict[str, Any]) -> None:
        keys = self._keys(session_id)
        self.redis.hset(keys.facts, fact_id, json.dumps(payload))
        self._expire_all(keys)

    def get_fact(self, session_id: str, fact_id: str) -> Optional[Dict[str, Any]]:
        keys = self._keys(session_id)
        raw = self.redis.hget(keys.facts, fact_id)
        self._expire_all(keys)
        if raw is None:
            return None
        return json.loads(raw)

    def delete_fact(self, session_id: str, fact_id: str) -> bool:
        keys = self._keys(session_id)
        removed = self.redis.hdel(keys.facts, fact_id)
        self._expire_all(keys)
        return bool(removed)

    def list_facts(self, session_id: str) -> Dict[str, Dict[str, Any]]:
        keys = self._keys(session_id)
        raw = self.redis.hgetall(keys.facts) or {}
        self._expire_all(keys)
        return {fact_id: json.loads(payload) for fact_id, payload in raw.items()}

    def increment_counter(self, session_id: str, name: str, delta: int = 1) -> int:
        keys = self._keys(session_id)
        current = self.redis.zincrby(keys.counters, delta, name)
        self._expire_all(keys)
        return int(current)

    def next_sequence(self, session_id: str, name: str) -> int:
        keys = self._keys(session_id)
        current = self.redis.zincrby(keys.sequences, 1, name)
        self._expire_all(keys)
        return int(current)

    def set_metadata(self, session_id: str, key: str, value: Any) -> None:
        keys = self._keys(session_id)
        self.redis.hset(keys.metadata, key, json.dumps(value))
        self._expire_all(keys)

    def get_metadata(self, session_id: str, key: str) -> Any:
        keys = self._keys(session_id)
        raw = self.redis.hget(keys.metadata, key)
        self._expire_all(keys)
        if raw is None:
            return None
        return json.loads(raw)


def get_session_storage() -> SessionStorage:
    redis_client = get_redis_client()
    if redis_client is not None:
        return RedisSessionStorage(redis_client=redis_client)

    env = settings.FLUXRULES_ENV.lower()
    if env == "production":
        raise RuntimeError("Redis is required for session storage in production.")

    logger.warning("Redis unavailable; using in-memory session storage fallback.")
    return InMemorySessionStorage()
