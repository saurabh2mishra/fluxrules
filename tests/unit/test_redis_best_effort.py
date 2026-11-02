"""The Redis caches are best effort and never slow a request down.

Without a Redis server, the compiled-rule cache used to build a new client per
call with redis-py's default retries, so every rule write waited seconds for
connections that could not succeed. These tests count connection attempts
instead of timing them.
"""

from __future__ import annotations

from typing import Any

import pytest

pytest.importorskip("redis")

import redis  # noqa: E402

from fluxrules.services.validation import _compiled_cache  # noqa: E402


class _Clients:
    """Stand-in for ``redis.Redis`` that records each client and ping."""

    def __init__(self, *, up: bool) -> None:
        self.up = up
        self.built: list[dict[str, Any]] = []
        self.pings = 0
        self.store: dict[str, Any] = {}

    def __call__(self, **kwargs: Any) -> Any:
        self.built.append(kwargs)
        clients = self

        class _Client:
            def ping(self) -> bool:
                clients.pings += 1
                if not clients.up:
                    raise redis.ConnectionError("no server")
                return True

            def get(self, key: str) -> Any:
                if not clients.up:
                    raise redis.ConnectionError("no server")
                return clients.store.get(key)

            def set(self, key: str, value: Any, *, ex: int) -> None:
                if not clients.up:
                    raise redis.ConnectionError("no server")
                clients.store[key] = value

            def delete(self, key: str) -> None:
                clients.store.pop(key, None)

            def close(self) -> None:
                pass

        return _Client()


@pytest.fixture(autouse=True)
def _fresh_state(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(_compiled_cache, "_redis_client", None)
    monkeypatch.setattr(_compiled_cache, "_redis_down_until", 0.0)
    monkeypatch.setattr(_compiled_cache, "_redis_missing", False)


@pytest.fixture()
def clock(monkeypatch: pytest.MonkeyPatch) -> list[float]:
    now = [1000.0]
    monkeypatch.setattr(_compiled_cache.time, "monotonic", lambda: now[0])
    return now


class TestCompiledCacheRedis:
    def test_reads_and_writes_skip_a_down_server(self, monkeypatch, clock) -> None:  # type: ignore[no-untyped-def]
        clients = _Clients(up=False)
        monkeypatch.setattr(redis, "Redis", clients)

        for _ in range(5):
            assert _compiled_cache._get_redis("payments") is None
            _compiled_cache._set_redis("payments", [{"id": 1}])

        assert len(clients.built) == 1

    def test_invalidate_always_tries(self, monkeypatch, clock) -> None:  # type: ignore[no-untyped-def]
        # Skipping a delete would leave stale compiled rules in Redis for other
        # processes, so invalidation ignores the wait (one fast attempt each,
        # with no retries).
        clients = _Clients(up=False)
        monkeypatch.setattr(redis, "Redis", clients)
        _compiled_cache._get_redis("payments")  # starts the wait

        for _ in range(3):
            _compiled_cache.invalidate("payments")
        assert len(clients.built) == 4

    def test_invalidate_during_the_wait_deletes_stale_rules(self, monkeypatch, clock) -> None:  # type: ignore[no-untyped-def]
        clients = _Clients(up=True)
        monkeypatch.setattr(redis, "Redis", clients)
        _compiled_cache._set_redis("payments", [{"id": 1}])
        assert clients.store

        # A brief outage starts the wait; Redis comes back within it.
        clients.up = False
        _compiled_cache._get_redis("payments")
        clients.up = True

        _compiled_cache.invalidate("payments")
        assert "fluxrules:compiled:payments" not in clients.store

    def test_unreadable_entry_is_not_an_outage(self, monkeypatch, clock) -> None:  # type: ignore[no-untyped-def]
        clients = _Clients(up=True)
        monkeypatch.setattr(redis, "Redis", clients)
        clients.store["fluxrules:compiled:payments"] = "{not json"

        assert _compiled_cache._get_redis("payments") is None
        assert _compiled_cache._get_redis_client() is not None
        assert _compiled_cache._redis_down_until == 0.0

    def test_missing_redis_package_is_never_retried(self, monkeypatch, clock) -> None:  # type: ignore[no-untyped-def]
        import builtins

        real_import = builtins.__import__

        def no_redis(name, *args, **kwargs):  # type: ignore[no-untyped-def]
            if name.startswith("redis"):
                raise ImportError(name)
            return real_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", no_redis)
        assert _compiled_cache._get_redis_client() is None
        monkeypatch.setattr(builtins, "__import__", real_import)
        assert _compiled_cache._get_redis_client(ignore_wait=True) is None

    def test_tries_again_after_the_wait(self, monkeypatch, clock) -> None:  # type: ignore[no-untyped-def]
        clients = _Clients(up=False)
        monkeypatch.setattr(redis, "Redis", clients)
        assert _compiled_cache._get_redis_client() is None

        clock[0] += _compiled_cache._REDIS_RETRY_SECONDS - 1
        assert _compiled_cache._get_redis_client() is None
        assert len(clients.built) == 1

        clients.up = True
        clock[0] += 2
        assert _compiled_cache._get_redis_client() is not None
        assert len(clients.built) == 2

    def test_running_server_uses_one_shared_client(self, monkeypatch, clock) -> None:  # type: ignore[no-untyped-def]
        clients = _Clients(up=True)
        monkeypatch.setattr(redis, "Redis", clients)

        _compiled_cache._set_redis("payments", [{"id": 1}])
        assert _compiled_cache._get_redis("payments") == [{"id": 1}]
        _compiled_cache.invalidate("payments")
        assert _compiled_cache._get_redis("payments") is None

        assert len(clients.built) == 1
        assert clients.pings == 1

    def test_client_has_short_timeouts_and_no_retries(self, monkeypatch, clock) -> None:  # type: ignore[no-untyped-def]
        clients = _Clients(up=True)
        monkeypatch.setattr(redis, "Redis", clients)
        _compiled_cache._get_redis_client()

        options = clients.built[0]
        assert options["socket_timeout"] == options["socket_connect_timeout"] == 0.5
        assert options["retry"].get_retries() == 0

    def test_failure_on_a_live_client_starts_the_wait(self, monkeypatch, clock) -> None:  # type: ignore[no-untyped-def]
        clients = _Clients(up=True)
        monkeypatch.setattr(redis, "Redis", clients)
        assert _compiled_cache._get_redis_client() is not None

        clients.up = False  # the server goes away
        assert _compiled_cache._get_redis("payments") is None
        assert _compiled_cache._get_redis_client() is None
        assert len(clients.built) == 1


class TestFailuresStartTheWait:
    def test_failed_write(self, monkeypatch, clock) -> None:  # type: ignore[no-untyped-def]
        clients = _Clients(up=True)
        monkeypatch.setattr(redis, "Redis", clients)
        assert _compiled_cache._get_redis_client() is not None

        clients.up = False
        _compiled_cache._set_redis("payments", [{"id": 1}])
        assert _compiled_cache._redis_client is None
        assert _compiled_cache._redis_down_until > clock[0]

    def test_failed_invalidate(self, monkeypatch, clock) -> None:  # type: ignore[no-untyped-def]
        clients = _Clients(up=True)
        monkeypatch.setattr(redis, "Redis", clients)
        client = _compiled_cache._get_redis_client()

        def broken_delete(key: str) -> None:
            raise redis.ConnectionError("gone")

        monkeypatch.setattr(client, "delete", broken_delete)
        _compiled_cache.invalidate("payments")
        assert _compiled_cache._redis_client is None
        assert _compiled_cache._redis_down_until > clock[0]
