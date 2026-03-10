"""
Compiled rule cache — avoids recompiling rules on every validation request.

Two-tier cache:
  1. In-memory LRU (per-process, fast, 60s TTL)
  2. Redis (shared across processes, 5min TTL)

Cache keys are scoped by group for group-scoped validation.
Invalidated when rules are created / updated / deleted.
"""
from __future__ import annotations

import hashlib
import json
import logging
import threading
import time
from typing import Any, Dict, List, Optional

from app.compiler.rule_compiler import CompiledRule, RuleCompiler
from app.validation._interval_index import IntervalIndex
from app.validation._normalization import Interval

logger = logging.getLogger(__name__)

_compiler = RuleCompiler()

# ---------------------------------------------------------------------------
# In-memory cache (per-process)
# ---------------------------------------------------------------------------
_LOCAL_CACHE: Dict[str, List[CompiledRule]] = {}
_LOCAL_CACHE_TIMES: Dict[str, float] = {}
_LOCAL_CACHE_TTL = 60  # seconds

# Index cache: pre-built IntervalIndex per group
_INDEX_CACHE: Dict[str, IntervalIndex] = {}
_INDEX_CACHE_TIMES: Dict[str, float] = {}
_INDEX_CACHE_TTL = 60

# Content hash to detect staleness without full recompile
_CONTENT_HASH: Dict[str, str] = {}

_lock = threading.Lock()


def _local_key(group: Optional[str]) -> str:
    return f"compiled:{group or '__all__'}"


def _index_key(group: Optional[str]) -> str:
    return f"index:{group or '__all__'}"


def _hash_payloads(payloads: List[Dict[str, Any]]) -> str:
    """Cheap content fingerprint for staleness detection."""
    raw = json.dumps(payloads, sort_keys=True, default=str)
    return hashlib.md5(raw.encode()).hexdigest()


# ---------------------------------------------------------------------------
# Local compiled-rules cache
# ---------------------------------------------------------------------------

def _get_local(group: Optional[str]) -> Optional[List[CompiledRule]]:
    key = _local_key(group)
    with _lock:
        if key in _LOCAL_CACHE:
            if (time.time() - _LOCAL_CACHE_TIMES.get(key, 0)) < _LOCAL_CACHE_TTL:
                return _LOCAL_CACHE[key]
            else:
                del _LOCAL_CACHE[key]
    return None


def _set_local(group: Optional[str], compiled: List[CompiledRule]) -> None:
    key = _local_key(group)
    with _lock:
        _LOCAL_CACHE[key] = compiled
        _LOCAL_CACHE_TIMES[key] = time.time()


# ---------------------------------------------------------------------------
# Local index cache
# ---------------------------------------------------------------------------

def _get_index(group: Optional[str]) -> Optional[IntervalIndex]:
    key = _index_key(group)
    with _lock:
        if key in _INDEX_CACHE:
            if (time.time() - _INDEX_CACHE_TIMES.get(key, 0)) < _INDEX_CACHE_TTL:
                return _INDEX_CACHE[key]
            else:
                del _INDEX_CACHE[key]
    return None


def _set_index(group: Optional[str], index: IntervalIndex) -> None:
    key = _index_key(group)
    with _lock:
        _INDEX_CACHE[key] = index
        _INDEX_CACHE_TIMES[key] = time.time()


# ---------------------------------------------------------------------------
# Redis cache helpers (best-effort, never blocks)
# ---------------------------------------------------------------------------
_REDIS_PREFIX = "fluxrules:compiled:"
_REDIS_TTL = 300  # 5 minutes


def _redis_key(group: Optional[str]) -> str:
    return f"{_REDIS_PREFIX}{group or '__all__'}"


def _get_redis(group: Optional[str]) -> Optional[List[Dict[str, Any]]]:
    try:
        from app.utils.redis_client import get_redis_client
        client = get_redis_client()
        if client is None:
            return None
        raw = client.get(_redis_key(group))
        if raw:
            return json.loads(raw)
    except Exception as exc:
        logger.debug("Redis compiled-cache read failed: %s", exc)
    return None


def _set_redis(group: Optional[str], payloads: List[Dict[str, Any]]) -> None:
    try:
        from app.utils.redis_client import get_redis_client
        client = get_redis_client()
        if client is None:
            return
        client.setex(_redis_key(group), _REDIS_TTL, json.dumps(payloads, default=str))
    except Exception as exc:
        logger.debug("Redis compiled-cache write failed: %s", exc)


# ---------------------------------------------------------------------------
# Index builder (builds IntervalIndex from compiled rules)
# ---------------------------------------------------------------------------

def _build_index(compiled: List[CompiledRule]) -> IntervalIndex:
    """Build an IntervalIndex from compiled rules using bulk construction."""
    from app.validation.conflict_detection import _decompose_or_branches, _branch_numeric_intervals

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


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def get_compiled_rules(
    rule_payloads: List[Dict[str, Any]],
    group: Optional[str] = None,
) -> List[CompiledRule]:
    """
    Return compiled rules, using caches when possible.

    ``rule_payloads`` is only used on a cache miss — the caller must supply the
    raw rule dicts so we can compile them.
    """
    # 1. local cache
    cached = _get_local(group)
    if cached is not None:
        return cached

    # 2. Redis cache
    redis_payloads = _get_redis(group)
    if redis_payloads is not None:
        compiled = _compiler.compile_rules(redis_payloads)
        _set_local(group, compiled)
        return compiled

    # 3. compile from supplied payloads
    compiled = _compiler.compile_rules(rule_payloads)
    _set_local(group, compiled)
    _set_redis(group, rule_payloads)
    return compiled


def get_compiled_rules_with_index(
    rule_payloads: List[Dict[str, Any]],
    group: Optional[str] = None,
) -> tuple[List[CompiledRule], IntervalIndex]:
    """
    Return compiled rules AND a pre-built IntervalIndex.

    Both are cached so repeated calls (e.g. bulk validation of N candidates in
    the same group) don't rebuild.
    """
    compiled = get_compiled_rules(rule_payloads, group)

    index = _get_index(group)
    if index is not None:
        return compiled, index

    index = _build_index(compiled)
    _set_index(group, index)
    return compiled, index


def invalidate(group: Optional[str] = None) -> None:
    """
    Invalidate the compiled-rule cache AND the index cache.

    If ``group`` is None, flush everything.
    """
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
        from app.utils.redis_client import get_redis_client
        client = get_redis_client()
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
