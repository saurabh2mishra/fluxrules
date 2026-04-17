import json
import logging

import pytest

from app.execution.storage_backend import (
    InMemorySessionStorage,
    RedisSessionStorage,
    get_session_storage,
)


class FakeRedis:
    def __init__(self):
        self.hashes = {}
        self.sorted_sets = {}
        self.expirations = {}

    def hset(self, key, field, value):
        self.hashes.setdefault(key, {})[field] = value
        return 1

    def hget(self, key, field):
        return self.hashes.get(key, {}).get(field)

    def hdel(self, key, field):
        if field in self.hashes.get(key, {}):
            del self.hashes[key][field]
            return 1
        return 0

    def hgetall(self, key):
        return dict(self.hashes.get(key, {}))

    def zincrby(self, key, amount, member):
        bucket = self.sorted_sets.setdefault(key, {})
        bucket[member] = float(bucket.get(member, 0.0)) + float(amount)
        return bucket[member]

    def expire(self, key, ttl):
        self.expirations[key] = ttl
        return True


@pytest.fixture
def redis_fixture():
    return FakeRedis()


def test_redis_session_storage_uses_hashes_sorted_sets_and_ttl(redis_fixture):
    storage = RedisSessionStorage(redis_fixture, ttl_seconds=90)
    sid = "session-a"

    storage.set_fact(sid, "fact-1", {"x": 1})
    assert storage.get_fact(sid, "fact-1") == {"x": 1}
    assert storage.list_facts(sid) == {"fact-1": {"x": 1}}

    assert storage.increment_counter(sid, "hits") == 1
    assert storage.increment_counter(sid, "hits", delta=2) == 3
    assert storage.next_sequence(sid, "seq") == 1
    assert storage.next_sequence(sid, "seq") == 2

    storage.set_metadata(sid, "status", {"ready": True})
    assert storage.get_metadata(sid, "status") == {"ready": True}

    assert storage.delete_fact(sid, "fact-1") is True
    assert storage.get_fact(sid, "fact-1") is None

    keys = [
        f"session:{sid}:facts",
        f"session:{sid}:counters",
        f"session:{sid}:sequences",
        f"session:{sid}:metadata",
    ]
    for key in keys:
        assert redis_fixture.expirations[key] == 90

    assert redis_fixture.hashes[f"session:{sid}:metadata"]["status"] == json.dumps({"ready": True})
    assert redis_fixture.sorted_sets[f"session:{sid}:counters"]["hits"] == 3.0
    assert redis_fixture.sorted_sets[f"session:{sid}:sequences"]["seq"] == 2.0


def test_get_session_storage_production_without_redis_raises(monkeypatch):
    monkeypatch.setattr("app.execution.storage_backend.get_redis_client", lambda: None)
    monkeypatch.setattr("app.execution.storage_backend.settings.FLUXRULES_ENV", "production")

    with pytest.raises(RuntimeError, match="Redis is required"):
        get_session_storage()


def test_get_session_storage_development_without_redis_falls_back_with_warning(monkeypatch, caplog):
    monkeypatch.setattr("app.execution.storage_backend.get_redis_client", lambda: None)
    monkeypatch.setattr("app.execution.storage_backend.settings.FLUXRULES_ENV", "development")

    with caplog.at_level(logging.WARNING):
        storage = get_session_storage()

    assert isinstance(storage, InMemorySessionStorage)
    assert "Redis unavailable; using in-memory session storage fallback" in caplog.text


def test_get_session_storage_returns_redis_storage_when_available(monkeypatch, redis_fixture):
    monkeypatch.setattr("app.execution.storage_backend.get_redis_client", lambda: redis_fixture)
    monkeypatch.setattr("app.execution.storage_backend.settings.FLUXRULES_ENV", "production")

    storage = get_session_storage()

    assert isinstance(storage, RedisSessionStorage)
