"""Unit tests for the ``RuleLoader`` fallback chain.

The loader tries three sources in order: cache -> repository -> local in-memory
cache. These tests exercise every hop, including the degraded-mode fallback and
the failure-of-all-sources path, using small fakes for the cache and repository.
"""

from __future__ import annotations

from typing import Any

import pytest

from fluxrules.services.rule_loader import RuleLoader


class FakeCache:
    """Minimal ``RuleCachePort``-shaped double with fault injection."""

    def __init__(self, value: Any = None, *, get_raises: bool = False) -> None:
        self._value = value
        self._get_raises = get_raises
        self.set_calls: list[tuple[int, int, Any]] = []
        self.set_raises = False

    def get(self, ruleset_id: int, version: int) -> Any | None:
        if self._get_raises:
            raise RuntimeError("cache down")
        return self._value

    def set(self, ruleset_id: int, version: int, network: Any, ttl_seconds: int = 3600) -> None:
        if self.set_raises:
            raise RuntimeError("cache write down")
        self.set_calls.append((ruleset_id, version, network))

    def invalidate(self, ruleset_id: int) -> None:  # pragma: no cover - unused here
        ...

    def get_stats(self) -> dict[str, Any]:  # pragma: no cover - unused here
        return {}


class FakeRepo:
    def __init__(self, value: Any = None, *, raises: bool = False) -> None:
        self._value = value
        self._raises = raises

    def get(self, ruleset_id: int) -> Any | None:
        if self._raises:
            raise RuntimeError("repo down")
        return self._value


def test_returns_from_cache_when_present() -> None:
    cache = FakeCache(value="cached-network")
    loader = RuleLoader(cache=cache, repository=FakeRepo(value="repo-network"))
    assert loader.load_rules(1, 1) == "cached-network"


def test_falls_back_to_repository_on_cache_miss_and_populates_caches() -> None:
    cache = FakeCache(value=None)
    loader = RuleLoader(cache=cache, repository=FakeRepo(value="repo-network"))

    assert loader.load_rules(7, 2) == "repo-network"
    # Repository result is written back to the shared cache...
    assert cache.set_calls == [(7, 2, "repo-network")]
    # ...and into the degraded-mode local cache.
    assert loader.local_cache["7:2"] == "repo-network"


def test_falls_back_to_repository_when_cache_raises() -> None:
    cache = FakeCache(get_raises=True)
    loader = RuleLoader(cache=cache, repository=FakeRepo(value="repo-network"))
    assert loader.load_rules(1, 1) == "repo-network"


def test_cache_write_failure_does_not_break_repository_path() -> None:
    cache = FakeCache(value=None)
    cache.set_raises = True
    loader = RuleLoader(cache=cache, repository=FakeRepo(value="repo-network"))
    # Even though writing back to cache fails, the repository value is returned.
    assert loader.load_rules(3, 1) == "repo-network"
    assert loader.local_cache["3:1"] == "repo-network"


def test_uses_local_cache_when_cache_and_repository_fail() -> None:
    cache = FakeCache(get_raises=True)
    loader = RuleLoader(
        cache=cache,
        repository=FakeRepo(raises=True),
        local_cache={"5:1": "degraded-network"},
    )
    assert loader.load_rules(5, 1) == "degraded-network"


def test_returns_none_when_all_sources_fail() -> None:
    cache = FakeCache(get_raises=True)
    loader = RuleLoader(cache=cache, repository=FakeRepo(raises=True))
    assert loader.load_rules(99, 1) is None


def test_repository_miss_falls_through_to_local_cache() -> None:
    # Cache misses (None) and the repository also has no such ruleset (None),
    # so the loader must fall through to the degraded local cache.
    loader = RuleLoader(
        cache=FakeCache(value=None),
        repository=FakeRepo(value=None),
        local_cache={"8:1": "degraded"},
    )
    assert loader.load_rules(8, 1) == "degraded"


def test_repository_miss_with_empty_local_cache_returns_none() -> None:
    loader = RuleLoader(cache=FakeCache(value=None), repository=FakeRepo(value=None))
    assert loader.load_rules(8, 1) is None


def test_default_version_is_one() -> None:
    cache = FakeCache(value=None)
    loader = RuleLoader(cache=cache, repository=FakeRepo(value="repo-network"))
    loader.load_rules(11)  # version defaults to 1
    assert loader.local_cache["11:1"] == "repo-network"


@pytest.mark.parametrize("provided", [None, {"a:1": "seed"}])
def test_local_cache_initialisation(provided: dict[str, Any] | None) -> None:
    loader = RuleLoader(cache=FakeCache(), repository=FakeRepo(), local_cache=provided)
    if provided is None:
        assert loader.local_cache == {}
    else:
        assert loader.local_cache == provided
