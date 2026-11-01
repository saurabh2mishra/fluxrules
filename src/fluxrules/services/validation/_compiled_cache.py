"""
Compiled rule cache - avoids recompiling rules on every validation request.

Two-tier cache:
  1. In-memory LRU (per-process, fast, 60s TTL)
  2. Redis (shared across processes, 5min TTL) - optional via [redis] extra

Cache keys are scoped by group for group-scoped validation.
Invalidated when rules are created / updated / deleted.
"""

from __future__ import annotations

import hashlib
import json
import logging
import threading
import time
from typing import Any

from fluxrules.services.compilation.rule_compiler import CompiledRule, RuleCompiler
from fluxrules.services.validation._interval_index import IntervalIndex

logger = logging.getLogger(__name__)

_compiler = RuleCompiler()

#  In-memory cache (per-process)
_LOCAL_CACHE: dict[str, list[CompiledRule]] = {}
_LOCAL_CACHE_TIMES: dict[str, float] = {}
_LOCAL_CACHE_TTL = 60  # seconds

# Index cache
_INDEX_CACHE: dict[str, IntervalIndex] = {}
_INDEX_CACHE_TIMES: dict[str, float] = {}
_INDEX_CACHE_TTL = 60

_CONTENT_HASH: dict[str | None, str] = {}
_lock = threading.Lock()


def _local_key(group: str | None) -> str:
    return f"compiled:{group or '__all__'}"


def _index_key(group: str | None) -> str:
    return f"index:{group or '__all__'}"


def _hash_payloads(payloads: list[dict[str, Any]]) -> str:
    raw = json.dumps(payloads, sort_keys=True, default=str)
    return hashlib.md5(raw.encode(), usedforsecurity=False).hexdigest()


#  Local compiled-rules cache


def _get_local(group: str | None) -> list[CompiledRule] | None:
    key = _local_key(group)
    with _lock:
        if key in _LOCAL_CACHE:
            if (time.time() - _LOCAL_CACHE_TIMES.get(key, 0)) < _LOCAL_CACHE_TTL:
                return _LOCAL_CACHE[key]
            else:
                del _LOCAL_CACHE[key]
    return None


def _set_local(group: str | None, compiled: list[CompiledRule]) -> None:
    key = _local_key(group)
    with _lock:
        _LOCAL_CACHE[key] = compiled
        _LOCAL_CACHE_TIMES[key] = time.time()


#  Local index cache


def _get_index(group: str | None) -> IntervalIndex | None:
    key = _index_key(group)
    with _lock:
        if key in _INDEX_CACHE:
            if (time.time() - _INDEX_CACHE_TIMES.get(key, 0)) < _INDEX_CACHE_TTL:
                return _INDEX_CACHE[key]
            else:
                del _INDEX_CACHE[key]
    return None


def _set_index(group: str | None, index: IntervalIndex) -> None:
    key = _index_key(group)
    with _lock:
        _INDEX_CACHE[key] = index
        _INDEX_CACHE_TIMES[key] = time.time()


#  Redis cache helpers (best-effort, never blocks)
_REDIS_PREFIX = "fluxrules:compiled:"
_REDIS_TTL = 300


def _redis_key(group: str | None) -> str:
    return f"{_REDIS_PREFIX}{group or '__all__'}"


# The Redis tier is best effort: it must never slow a request down. One client
# is shared per process, with short timeouts and no retries, and after a
# failure Redis is skipped for _REDIS_RETRY_SECONDS before the next attempt.
# (A new client per call, with redis-py's default retries, cost seconds per
# call on a server without Redis.)
_REDIS_TIMEOUT_SECONDS = 0.5
_REDIS_RETRY_SECONDS = 30.0
_redis_client: Any = None
_redis_down_until = 0.0


def _get_redis_client():
    """Return the shared Redis client, or ``None`` while Redis is unavailable."""
    global _redis_client, _redis_down_until
    if _redis_client is not None:
        return _redis_client
    if time.monotonic() < _redis_down_until:
        return None
    try:
        import redis as _redis
        from redis.backoff import NoBackoff
        from redis.retry import Retry
    except ImportError:
        _redis_down_until = float("inf")  # not installed: never try again
        return None
    try:
        client = _redis.Redis(
            socket_timeout=_REDIS_TIMEOUT_SECONDS,
            socket_connect_timeout=_REDIS_TIMEOUT_SECONDS,
            retry=Retry(NoBackoff(), 0),
        )
        client.ping()
    except Exception as exc:
        logger.debug("Redis compiled-cache unavailable: %s", exc)
        _mark_redis_down()
        return None
    _redis_client = client
    return client


def _mark_redis_down() -> None:
    """Drop the shared client and skip Redis for ``_REDIS_RETRY_SECONDS``."""
    global _redis_client, _redis_down_until
    _redis_client = None
    _redis_down_until = time.monotonic() + _REDIS_RETRY_SECONDS


def _get_redis(group: str | None) -> list[dict[str, Any]] | None:
    try:
        client = _get_redis_client()
        if client is None:
            return None
        raw = client.get(_redis_key(group))
        if raw:
            return json.loads(raw)
    except Exception as exc:
        logger.debug("Redis compiled-cache read failed: %s", exc)
        _mark_redis_down()
    return None


def _set_redis(group: str | None, payloads: list[dict[str, Any]]) -> None:
    try:
        client = _get_redis_client()
        if client is None:
            return
        client.set(
            _redis_key(group),
            json.dumps(payloads, default=str),
            ex=_REDIS_TTL,
        )
    except Exception as exc:
        logger.debug("Redis compiled-cache write failed: %s", exc)
        _mark_redis_down()


#  Index builder


def _build_index(compiled: list[CompiledRule]) -> IntervalIndex:
    from fluxrules.services.validation.conflict_detection import (
        _branch_numeric_intervals,
        _decompose_or_branches,
    )

    entries = []
    for rule in compiled:
        for branch in _decompose_or_branches(rule.source_condition):
            for field, ivs in _branch_numeric_intervals(branch).items():
                for iv in ivs:
                    entries.append((rule.id, field, iv))

    index = IntervalIndex()
    if entries:
        index.bulk_build(entries)
    return index


#  Public API


def get_compiled_rules(
    rule_payloads: list[dict[str, Any]],
    group: str | None = None,
) -> list[CompiledRule]:
    cached = _get_local(group)
    if cached is not None:
        return cached

    redis_payloads = _get_redis(group)
    if redis_payloads is not None:
        compiled = _compiler.compile_rules(redis_payloads)
        _set_local(group, compiled)
        return compiled

    compiled = _compiler.compile_rules(rule_payloads)
    _set_local(group, compiled)
    _set_redis(group, rule_payloads)
    return compiled


def get_compiled_rules_with_index(
    rule_payloads: list[dict[str, Any]],
    group: str | None = None,
) -> tuple[list[CompiledRule], IntervalIndex]:
    compiled = get_compiled_rules(rule_payloads, group)
    index = _get_index(group)
    if index is not None:
        return compiled, index
    index = _build_index(compiled)
    _set_index(group, index)
    return compiled, index


def invalidate(group: str | None = None) -> None:
    with _lock:
        if group is None:
            _LOCAL_CACHE.clear()
            _LOCAL_CACHE_TIMES.clear()
            _INDEX_CACHE.clear()
            _INDEX_CACHE_TIMES.clear()
            _CONTENT_HASH.clear()
        else:
            for prefix_key in [_local_key(group), _local_key(None)]:
                _LOCAL_CACHE.pop(prefix_key, None)
                _LOCAL_CACHE_TIMES.pop(prefix_key, None)
            for prefix_key in [_index_key(group), _index_key(None)]:
                _INDEX_CACHE.pop(prefix_key, None)
                _INDEX_CACHE_TIMES.pop(prefix_key, None)
            _CONTENT_HASH.pop(group, None)
            _CONTENT_HASH.pop(None, None)

    try:
        client = _get_redis_client()
        if client is None:
            return
        if group is None:
            for k in client.scan_iter(match=f"{_REDIS_PREFIX}*"):
                client.delete(k)
        else:
            client.delete(_redis_key(group))
            client.delete(_redis_key(None))
    except Exception as exc:
        logger.debug("Redis compiled-cache invalidation failed: %s", exc)
        _mark_redis_down()
