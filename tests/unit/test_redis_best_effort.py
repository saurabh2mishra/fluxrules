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


@pytest.fixture()
def clock(monkeypatch: pytest.MonkeyPatch) -> list[float]:
    now = [1000.0]
    monkeypatch.setattr(_compiled_cache.time, "monotonic", lambda: now[0])
    return now


class TestCompiledCacheRedis:
    def test_down_server_is_tried_once_then_skipped(self, monkeypatch, clock) -> None:  # type: ignore[no-untyped-def]
        clients = _Clients(up=False)
        monkeypatch.setattr(redis, "Redis", clients)

        for _ in range(5):
            assert _compiled_cache._get_redis("payments") is None
            _compiled_cache._set_redis("payments", [{"id": 1}])
            _compiled_cache.invalidate("payments")

        assert len(clients.built) == 1

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


class TestSharedApiClient:
    @pytest.fixture(autouse=True)
    def _fresh_api_state(self, monkeypatch: pytest.MonkeyPatch) -> None:
        pytest.importorskip("pydantic_settings")
        from fluxrules.api.utils import redis_client

        monkeypatch.setattr(redis_client, "_redis_client", None)
        monkeypatch.setattr(redis_client, "_redis_available", None)

    def test_probe_has_no_retries_and_failure_is_remembered(self, monkeypatch) -> None:  # type: ignore[no-untyped-def]
        from fluxrules.api.utils import redis_client

        clients = _Clients(up=False)
        monkeypatch.setattr(redis_client.redis, "Redis", clients)

        assert redis_client.get_redis_client() is None
        assert redis_client.get_redis_client() is None
        assert len(clients.built) == 1
        assert clients.built[0]["retry"].get_retries() == 0

    def test_kept_client_uses_default_retries(self, monkeypatch) -> None:  # type: ignore[no-untyped-def]
        from fluxrules.api.utils import redis_client

        clients = _Clients(up=True)
        monkeypatch.setattr(redis_client.redis, "Redis", clients)

        assert redis_client.get_redis_client() is not None
        probe, kept = clients.built
        assert probe["retry"].get_retries() == 0
        assert "retry" not in kept
