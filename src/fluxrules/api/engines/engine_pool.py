"""RuleEnginePool - build the rule network once, reuse it across requests.

Problem this solves
-------------------
``APIEngineAdapter.evaluate`` used to call ``engine.load_rules(rules)`` on *every*
request. For a Phreak engine ``load_rules`` clears and rebuilds the bit-mask
linker, segment caches, alpha pre-filter index and (optionally) recompiles every
condition - the single most expensive operation in the system - so paying it per
fact both collapses throughput and (when the engine is shared across requests)
races a half-built network against concurrent evaluations.

Design
------
The pool keeps a small, bounded **LRU of fully-built engines keyed by a stable
signature of the (already rule_id-filtered) rule set**. On a request:

1. Compute the rule-set signature (cheap, content-based).
2. If an engine for that signature is cached, return it (lock-free fast path).
3. Otherwise build a **new** engine, ``load_rules`` into it *completely*, then
   publish it under a short lock (build-fully-then-atomic-insert). Readers never
   observe a partially-loaded engine, and the previously-current engine is left
   untouched for any in-flight evaluations.

Because the held engines are used in **stateless** mode and stateless
``evaluate`` does not mutate shared engine state (thread-local leaf memo + pure
``BitMaskLinker.linked_rules_for``), a single cached engine is safe
to evaluate concurrently from many request threads.

The common API shapes benefit immediately:
- "evaluate against all rules (a group)": one signature → one engine, reused for
  every request at that rule version.
- "evaluate against an explicit ``rule_ids`` subset": repeated identical subsets
  reuse their engine; the LRU bounds memory for pathological churn.
"""

from __future__ import annotations

import json
import logging
import threading
import time
from collections import OrderedDict
from collections.abc import Callable
from typing import Any, cast

from fluxrules.engine import BaseEngine, get_engine

logger = logging.getLogger(__name__)


def rules_signature(rules: list[dict[str, Any]]) -> str:
    """Return a stable, content-based signature for a list of rule dicts.

    Two rule lists that would build an identical network (same ids, conditions,
    priorities, actions, tags - regardless of list order) produce the same
    signature. Values that are not JSON-serializable fall back to ``repr`` so the
    signature is always computable.
    """

    def _norm(rule: dict[str, Any]) -> tuple:
        return (
            rule.get("id"),
            json.dumps(
                rule.get("condition_dsl"),
                sort_keys=True,
                default=repr,
                separators=(",", ":"),
            ),
            rule.get("priority", 0),
            rule.get("action"),
            tuple(sorted(rule.get("tags", []) or [])),
            rule.get("group") or rule.get("domain"),
        )

    normalized = sorted(_norm(r) for r in rules)
    return json.dumps(normalized, default=repr, separators=(",", ":"))


class RuleEnginePool:
    """Bounded LRU cache of fully-built engines keyed by rule-set signature.

    Usage::

        pool = RuleEnginePool(engine_type="PHREAK")
        engine = pool.get(rules)        # builds once; reused on identical rules
        result = engine.evaluate(event)   # stateless, concurrency-safe (P0.2)

    Args:
        engine_type: engine registry name (e.g. ``"PHREAK"``).
        max_instances: maximum number of distinct rule-set networks to keep warm.
        engine_kwargs: forwarded to ``get_engine`` when building an engine.
    """

    def __init__(
        self,
        engine_type: str = "PHREAK",
        max_instances: int = 8,
        **engine_kwargs: Any,
    ) -> None:
        self._engine_type = engine_type
        self._engine_kwargs = engine_kwargs
        self._max_instances = max(1, max_instances)
        self._lock = threading.Lock()
        # signature -> built engine. OrderedDict gives us LRU ordering.
        self._engines: OrderedDict[str, BaseEngine] = OrderedDict()
        self._builds = 0  # how many times load_rules was actually paid
        self._hits = 0  # how many requests reused a warm engine
        self._evictions = 0  # how many warm engines were evicted (LRU)
        self._build_seconds_total = 0.0  # cumulative time spent building
        self._last_build_seconds = 0.0  # duration of the most recent build

    def get(
        self,
        rules: list[dict[str, Any]],
        *,
        signature: str | None = None,
    ) -> BaseEngine:
        """Return a fully-built engine for ``rules``, building only if needed.

        Args:
            rules: the (already filtered) rule dicts to load.
            signature: optional precomputed signature (skips re-hashing).

        Returns:
            A ready-to-evaluate engine whose loaded rules match ``rules``.
        """
        sig = signature if signature is not None else rules_signature(rules)

        # Fast path: lock-free read of an existing, fully-built engine.
        engine = self._engines.get(sig)
        if engine is not None:
            self._hits += 1
            # Mark as recently used. Reordering under the lock keeps the LRU
            # honest without blocking the common read.
            with self._lock:
                if sig in self._engines:
                    self._engines.move_to_end(sig)
            return engine

        # Slow path: build a NEW engine fully, then publish atomically.
        with self._lock:
            # Double-check: another thread may have built it while we waited.
            existing = self._engines.get(sig)
            if existing is not None:
                self._hits += 1
                self._engines.move_to_end(sig)
                return existing

            new_engine = get_engine(self._engine_type, **self._engine_kwargs)
            build_start = time.perf_counter()
            new_engine.load_rules(cast("list[Any]", rules))  # build COMPLETELY before publishing
            build_seconds = time.perf_counter() - build_start
            self._builds += 1
            self._build_seconds_total += build_seconds
            self._last_build_seconds = build_seconds
            self._engines[sig] = new_engine
            self._engines.move_to_end(sig)
            # Evict least-recently-used networks beyond the cap.
            while len(self._engines) > self._max_instances:
                evicted_sig, _ = self._engines.popitem(last=False)
                self._evictions += 1
                logger.debug("RuleEnginePool evicted network %s", evicted_sig[:16])
            return new_engine

    def invalidate(self) -> None:
        """Drop all cached engines (e.g. after a rule create/update/delete)."""
        with self._lock:
            self._engines.clear()
        logger.info("RuleEnginePool invalidated; networks will rebuild on next request")

    @property
    def stats(self) -> dict[str, Any]:
        """Build/hit counters for observability (feeds P2.4 metrics).

        Includes engine-rebuild accounting (P2.4): ``builds`` is the number of
        ``load_rules`` rebuilds paid, ``last_build_seconds`` /
        ``avg_build_seconds`` their duration. A climbing ``builds`` rate with a
        low ``reuse_rate`` signals a **rebuild storm** (rule-set churn defeating
        the build-once cache) - alert on it.
        """
        total = self._hits + self._builds
        return {
            "warm_engines": len(self._engines),
            "max_instances": self._max_instances,
            "builds": self._builds,
            "hits": self._hits,
            "evictions": self._evictions,
            "reuse_rate": (self._hits / total) if total else 0.0,
            "last_build_seconds": self._last_build_seconds,
            "avg_build_seconds": (
                self._build_seconds_total / self._builds if self._builds else 0.0
            ),
        }

    def current_engine_metrics(self) -> dict[str, Any] | None:
        """Return observability metrics from the most-recently-used warm engine.

        Surfaces the per-engine P2.4 signals (alpha prune ratio, leaf-memo hit
        rate, candidates/fact, latency, working-memory size) for the network an
        operator is most likely serving traffic against. Returns ``None`` when
        no engine is warm or the engine type does not expose
        ``get_observability_metrics``.
        """
        engine: BaseEngine | None = None
        # The MRU engine is the last item in the OrderedDict.
        for eng in reversed(self._engines.values()):
            engine = eng
            break
        if engine is None:
            return None
        getter = getattr(engine, "get_observability_metrics", None)
        if getter is None:
            return None
        return getter()


def build_pool(
    engine_type: str = "PHREAK",
    max_instances: int = 8,
    **engine_kwargs: Any,
) -> RuleEnginePool:
    """Convenience factory mirroring ``get_engine`` ergonomics."""
    return RuleEnginePool(engine_type=engine_type, max_instances=max_instances, **engine_kwargs)


# Type alias for the rule-loader callback shape some call sites prefer.
RulesLoader = Callable[[], list[dict[str, Any]]]

__all__ = ["RuleEnginePool", "RulesLoader", "build_pool", "rules_signature"]
