"""Fact deduplication framework.

Real-world fact streams repeat: the same event payload (or a payload identical
in every field a rule cares about) arrives many times. Each repeat re-runs the
full CPU-bound ``engine.evaluate()`` for an answer that cannot change, because
``evaluate`` is a pure function of ``(rules, facts)`` in stateless mode.

This module memoizes that pure function: a fact is canonically hashed and the
``EvaluationResult`` is cached. On a cache hit the engine is skipped entirely.

Soundness
---------
The cache is keyed on the *canonical content* of the fact, so a hit returns the
exact result a fresh ``evaluate`` would have produced. The contract is identical
to ``test_dedup`` in the plan (§4.1): ``cached result == fresh evaluate``.

Caveats (enforced by the API):
- Only valid for **stateless** engines (``streaming_mode=False``). Streaming
  evaluation is order-dependent (it returns activation *deltas*), so memoizing
  by fact content would be unsound. :class:`DedupEvaluator` rejects streaming
  engines.
- The result's ``latency_ms`` reflects the *original* computation, not the cache
  hit. Hits are reported separately via :attr:`DedupStats`.

Backends
--------
- In-memory LRU (default) - bounded, no dependency, single-process.
- Redis (opt-in, behind the ``redis`` extra) - cross-process / cross-host dedup
  for the parallel worker pool. Only fired-rule ids are stored remotely (the
  small, serializable core of the result); the full result is reconstructed
  locally. Falls back to memory if Redis is unavailable.
"""

from __future__ import annotations

import json
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Any, Protocol

from fluxrules.engine.infrastructure.evaluation_result import EvaluationResult


def canonical_fact_key(facts: dict[str, Any]) -> str:
    """Return a stable, hashable key for ``facts``.

    Two fact dicts that are equal as mappings (same keys, same values,
    regardless of insertion order) produce the same key. Values that are not
    JSON-serializable fall back to ``repr`` so the key is always computable.
    """
    try:
        # ``sort_keys`` makes the key order-independent; ``default=repr`` keeps
        # it total over arbitrary value types (sets, tuples, custom objects).
        return json.dumps(facts, sort_keys=True, default=repr, separators=(",", ":"))
    except (TypeError, ValueError):
        # Last-resort canonicalization for exotic key types.
        return repr(sorted((str(k), repr(v)) for k, v in facts.items()))


@dataclass
class DedupStats:
    """Hit/miss counters for a :class:`DedupEvaluator`."""

    hits: int = 0
    misses: int = 0

    @property
    def total(self) -> int:
        return self.hits + self.misses

    @property
    def hit_rate(self) -> float:
        return self.hits / self.total if self.total else 0.0


class DedupBackend(Protocol):
    """Storage protocol for the fact -> result memo."""

    def get(self, key: str) -> EvaluationResult | None: ...

    def put(self, key: str, result: EvaluationResult) -> None: ...

    def clear(self) -> None: ...

    def __len__(self) -> int: ...


class LRUDedupBackend:
    """Bounded in-memory LRU cache of ``key -> EvaluationResult``."""

    def __init__(self, max_entries: int = 100_000) -> None:
        if max_entries <= 0:
            raise ValueError("max_entries must be positive")
        self._max = max_entries
        self._store: OrderedDict[str, EvaluationResult] = OrderedDict()

    def get(self, key: str) -> EvaluationResult | None:
        result = self._store.get(key)
        if result is not None:
            self._store.move_to_end(key)  # mark most-recently-used
        return result

    def put(self, key: str, result: EvaluationResult) -> None:
        self._store[key] = result
        self._store.move_to_end(key)
        while len(self._store) > self._max:
            self._store.popitem(last=False)  # evict least-recently-used

    def clear(self) -> None:
        self._store.clear()

    def __len__(self) -> int:
        return len(self._store)


class RedisDedupBackend:
    """Cross-process dedup backend backed by Redis.

    Only the serializable core of a result (fired rules, matched ids, actions)
    is stored remotely; the full :class:`EvaluationResult` is rebuilt on read.
    This keeps payloads tiny and avoids pickling engine-specific objects.

    Requires the optional ``redis`` extra. Construction fails loudly if Redis is
    not installed/reachable so callers can choose to fall back to
    :class:`LRUDedupBackend`.
    """

    def __init__(
        self,
        url: str = "redis://localhost:6379/0",
        *,
        namespace: str = "fluxrules:dedup",
        ttl_seconds: int | None = 3600,
        client: Any | None = None,
    ) -> None:
        if client is None:
            try:
                import redis  # type: ignore[import-untyped]
            except ImportError as exc:  # pragma: no cover - import guard
                raise RuntimeError(
                    "RedisDedupBackend requires the 'redis' extra: pip install 'fluxrules[redis]'"
                ) from exc
            client = redis.Redis.from_url(url)
        self._client = client
        self._ns = namespace
        self._ttl = ttl_seconds

    def _key(self, key: str) -> str:
        return f"{self._ns}:{key}"

    def get(self, key: str) -> EvaluationResult | None:
        raw = self._client.get(self._key(key))
        if not isinstance(raw, (str, bytes, bytearray)):
            return None
        data = json.loads(raw)
        return EvaluationResult(
            candidate_rule_ids=data.get("candidate_rule_ids", []),
            fired_rules=data.get("fired_rules", []),
            actions=data.get("actions", []),
            engine_type=data.get("engine_type", ""),
        )

    def put(self, key: str, result: EvaluationResult) -> None:
        payload = json.dumps(
            {
                "candidate_rule_ids": result.candidate_rule_ids,
                "fired_rules": result.fired_rules,
                "actions": result.actions,
                "engine_type": result.engine_type,
            },
            separators=(",", ":"),
        )
        if self._ttl is not None:
            self._client.set(self._key(key), payload, ex=self._ttl)
        else:
            self._client.set(self._key(key), payload)

    def clear(self) -> None:
        # Scoped clear: only delete this namespace's keys.
        for k in self._client.scan_iter(match=f"{self._ns}:*"):
            self._client.delete(k)

    def __len__(self) -> int:
        return sum(1 for _ in self._client.scan_iter(match=f"{self._ns}:*"))


@dataclass
class DedupEvaluator:
    """Memoizing wrapper around a stateless engine.

    Usage::

        engine = PhreakEngine(streaming_mode=False)
        engine.load_rules(rules)
        dedup = DedupEvaluator(engine)

        for fact in stream:
            result = dedup.evaluate(fact)   # skips engine on repeats

    The wrapped engine must be stateless; streaming engines are rejected because
    their results depend on evaluation order, not fact content alone.
    """

    engine: Any
    backend: DedupBackend = field(default_factory=LRUDedupBackend)
    stats: DedupStats = field(default_factory=DedupStats)

    def __post_init__(self) -> None:
        if getattr(self.engine, "_streaming_mode", False):
            raise ValueError(
                "DedupEvaluator requires a stateless engine "
                "(streaming_mode=False); streaming results are order-dependent "
                "and cannot be memoized by fact content."
            )

    def evaluate(self, facts: dict[str, Any], **kwargs: Any) -> EvaluationResult:
        """Return the cached result for ``facts`` or compute and cache it.

        ``kwargs`` (e.g. ``filters``) are forwarded to the engine on a miss and
        folded into the cache key so different filters never collide.
        """
        key = canonical_fact_key(facts)
        if kwargs:
            key = f"{key}|{canonical_fact_key(_normalize_kwargs(kwargs))}"

        cached = self.backend.get(key)
        if cached is not None:
            self.stats.hits += 1
            return cached

        self.stats.misses += 1
        result = self.engine.evaluate(facts, **kwargs)
        self.backend.put(key, result)
        return result

    def clear(self) -> None:
        """Drop all cached results and reset stats."""
        self.backend.clear()
        self.stats = DedupStats()


def _normalize_kwargs(kwargs: dict[str, Any]) -> dict[str, Any]:
    """Make kwargs hashable/serializable for inclusion in the cache key."""
    out: dict[str, Any] = {}
    for k, v in kwargs.items():
        out[k] = repr(v)
    return out
