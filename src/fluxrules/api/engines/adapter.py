"""API Adapter Layer - thin wrapper with API-specific features.

Responsibilities:
- Wraps main engine implementations with API-specific concerns
- Handles rule caching
- Collects evaluation metrics
- Converts typed results to API dict format
- Database session management

This is NOT an engine implementation. It coordinates features
around the main engines in fluxrules.engine module.
"""

import logging
import time
from typing import Any

from sqlalchemy.orm import Session

from fluxrules.api.engines.engine_pool import RuleEnginePool
from fluxrules.engine import BaseEngine, get_engine
from fluxrules.engine.infrastructure import EvaluationResult

logger = logging.getLogger(__name__)


class RuleCache:
    """Simple in-memory cache for rules with optional Redis support."""

    CACHE_KEY_PREFIX = "rule_engine:"
    CACHE_TTL = 300  # 5 minutes

    def __init__(self, enable_redis: bool = True):
        """Initialize rule cache.

        Args:
            enable_redis: Whether to attempt Redis connection
        """
        self._local_cache: dict[str, Any] = {}
        self._local_cache_times: dict[str, float] = {}
        self._local_cache_ttl = 60
        self._redis = None
        self._redis_available = False

        if enable_redis:
            try:
                from fluxrules.api.utils.redis_client import get_redis_client

                self._redis = get_redis_client()
                if self._redis is not None:
                    self._redis_available = True
            except Exception as e:
                logger.debug(f"Redis not available for caching: {e}")

    def get_rules(self, db: Session | None, group: str | None = None) -> list[dict[str, Any]]:
        """Get rules from cache or database.

        Args:
            db: Database session
            group: Optional group filter

        Returns:
            List of rule dictionaries
        """
        cache_key = f"rules:{group or 'all'}"

        # Check local cache first
        if self._is_local_cache_valid(cache_key):
            return self._local_cache.get(cache_key, [])

        # Check Redis if available
        if self._redis_available and self._redis is not None:
            try:
                import json

                cached = self._redis.get(self._get_cache_key(cache_key))
                if cached:
                    rules = json.loads(cached)
                    self._update_local_cache(cache_key, rules)
                    return rules
            except Exception as e:
                logger.debug(f"Redis cache error: {e}")

        # Load from database
        rules = self._load_rules_from_db(db, group)
        self._update_local_cache(cache_key, rules)
        self._update_redis_cache(cache_key, rules)
        return rules

    def clear(self) -> None:
        """Clear all cache."""
        self._local_cache.clear()
        self._local_cache_times.clear()

    def _get_cache_key(self, key: str) -> str:
        """Get Redis cache key."""
        return f"{self.CACHE_KEY_PREFIX}{key}"

    def _is_local_cache_valid(self, key: str) -> bool:
        """Check if local cache is still valid."""
        if key not in self._local_cache:
            return False
        cache_time = self._local_cache_times.get(key, 0)
        return (time.time() - cache_time) < self._local_cache_ttl

    def _update_local_cache(self, key: str, rules: list[dict[str, Any]]) -> None:
        """Update local cache."""
        self._local_cache[key] = rules
        self._local_cache_times[key] = time.time()

    def _update_redis_cache(self, key: str, rules: list[dict[str, Any]]) -> None:
        """Update Redis cache if available."""
        if self._redis_available and self._redis is not None:
            try:
                import json

                self._redis.set(
                    self._get_cache_key(key), json.dumps(rules), ex=self.CACHE_TTL
                )
            except Exception as e:
                logger.debug(f"Failed to update Redis cache: {e}")

    @staticmethod
    def _load_rules_from_db(db: Session | None, group: str | None = None) -> list[dict[str, Any]]:
        """Load rules from database.

        Args:
            db: Database session
            group: Optional group filter

        Returns:
            List of rule dictionaries
        """
        if not db:
            return []

        try:
            from fluxrules.api.models.rule import Rule

            query = db.query(Rule)
            if group:
                query = query.filter(Rule.group == group)

            rules = query.all()
            return [
                {
                    "id": r.id,
                    "name": r.name,
                    "priority": getattr(r, "priority", 0),
                    "condition_dsl": r.condition_dsl,
                    "action": getattr(r, "action", None),
                    "group": getattr(r, "group", None),
                    "tags": getattr(r, "tags", []),
                }
                for r in rules
            ]
        except Exception as e:
            logger.warning(f"Failed to load rules from database: {e}")
            return []


class APIEngineAdapter:
    """Thin adapter layer wrapping main engines with API features.

    This adapter:
    - Wraps the PHREAK engine
    - Adds caching layer for rules
    - Handles metrics collection
    - Converts results to API format
    - Manages database integration

    Example:
        adapter = APIEngineAdapter(
            engine_type="PHREAK",
            db=db_session,
            enable_cache=True,
            enable_metrics=True
        )
        result = adapter.evaluate(
            event={"amount": 1500, "user": "john"},
            rule_ids=None
        )
    """

    def __init__(
        self,
        engine_type: str = "PHREAK",
        db: Session | None = None,
        enable_cache: bool = True,
        enable_metrics: bool = True,
    ):
        """Initialize API adapter.

        Args:
            engine_type: Engine to use (PHREAK)
            db: Database session
            enable_cache: Whether to enable rule caching
            enable_metrics: Whether to collect metrics

        Raises:
            ValueError: If engine_type is invalid
        """
        # Validate and create the main engine (without passing db)
        try:
            self._engine: BaseEngine = get_engine(engine_type)
        except ValueError as e:
            raise ValueError(f"Invalid engine type '{engine_type}': {e}")

        self._engine_type = engine_type
        self._db = db
        self._enable_metrics = enable_metrics

        # Build-once engine cache. Rules are loaded into a held engine
        # keyed by a stable rule-set signature and reused across requests, so
        # the expensive load_rules/network rebuild is no longer paid per request.
        # Held engines run in stateless mode, which is concurrency-safe.
        # When metrics are enabled, the held engines collect operational
        # observability (alpha prune ratio, leaf-memo hit rate, latency) which the stats
        # endpoint surfaces.
        holder_kwargs: dict[str, Any] = {}
        if enable_metrics and engine_type.upper() == "PHREAK":
            holder_kwargs["enable_metrics"] = True
        self._holder = RuleEnginePool(engine_type=engine_type, **holder_kwargs)

        # Streaming-misuse guardrail: warn at most once if a streaming
        # engine is served behind this stateless request/response path (delta
        # semantics + sticky-routing required; see docs/sessions.md).
        self._streaming_misuse_warned = False

        # Optional caching layer
        self._cache = RuleCache(enable_redis=enable_cache) if enable_cache else None

        logger.info(
            f"APIEngineAdapter initialized with engine_type={engine_type}, "
            f"cache_enabled={enable_cache}, metrics_enabled={enable_metrics}"
        )

    def evaluate(
        self,
        event: dict[str, Any],
        rule_ids: list[int] | None = None,
        group: str | None = None,
        **kwargs,
    ) -> dict[str, Any]:
        """Evaluate event against rules with caching and metrics.

        Args:
            event: Event/fact data to evaluate
            rule_ids: Optional list of rule IDs to evaluate
            group: Optional rule group filter
            **kwargs: Additional arguments passed to engine

        Returns:
            Dict with API response format containing:
            - matched_rules: List of matching rule details
            - execution_order: Order rules fired
            - actions: List of actions triggered
            - explanations: Rule match explanations
            - engine_type: Engine used
            - stats: Performance statistics
        """
        start_time = time.time()

        try:
            # 1. Get rules (with caching if enabled)
            rules = self._get_rules(group, rule_ids)

            # 2. Filter by specific rule_ids if provided
            if rule_ids:
                rules_map = {r.get("id"): r for r in rules}
                rules = [rules_map[rid] for rid in rule_ids if rid in rules_map]

            # 3. Resolve a build-once engine for this exact rule set and
            # evaluate. The network is built only when the rule set changes;
            # identical rule sets reuse a warm, concurrency-safe engine.
            # This replaces the previous per-request load_rules rebuild.
            engine = self._holder.get(rules)
            self._warn_if_streaming_misuse(engine)
            result: EvaluationResult = engine.evaluate(event, **kwargs)

            # 4. Collect metrics
            latency_ms = (time.time() - start_time) * 1000
            if self._enable_metrics:
                self._collect_metrics(result, latency_ms, len(rules))

            # 5. Format and return API response
            return self._format_response(result, latency_ms)

        except Exception as e:
            logger.error(f"Evaluation error: {e}", exc_info=True)
            raise

    def get_stats(self) -> dict[str, Any]:
        """Get engine statistics, including operational observability.

        Returns:
            Dictionary with engine stats. The ``engine_holder`` block carries
            build-once / rebuild accounting and, when metrics are
            enabled for a PHREAK engine, an ``observability`` block with the
            per-engine signals (alpha prune ratio, candidates/fact, leaf-memo and
            node-memory hit rates, linked rules, eval latency p50/p95/p99,
            working-memory size). See ``docs/observability.md`` for alert
            thresholds.
        """
        stats = self._engine.get_stats()
        stats["engine_type"] = self._engine_type
        stats["caching_enabled"] = self._cache is not None
        stats["metrics_enabled"] = self._enable_metrics
        stats["engine_holder"] = self._holder.stats
        # Per-engine observability from the warm (most-recently-built) network.
        # Flag-gated: only surfaced when metrics were enabled for the adapter so
        # the default response stays lean (zero-overhead default).
        if self._enable_metrics:
            observability = self._holder.current_engine_metrics()
            if observability is not None:
                # Fold in the rebuild signal so the dashboard sees it alongside
                # the per-fact metrics (one engine cannot see its own rebuilds).
                holder_stats = self._holder.stats
                observability["engine_rebuilds"] = holder_stats["builds"]
                observability["engine_rebuild_last_seconds"] = holder_stats["last_build_seconds"]
                observability["engine_reuse_rate"] = holder_stats["reuse_rate"]
                stats["observability"] = observability
        return stats

    def reload_rules(self) -> None:
        """Reload rules from database, clearing cache.

        Invalidates both the rule dict cache and the build-once engine cache so
        the next request rebuilds the network from the current rule set.
        """
        if self._cache:
            self._cache.clear()
        self._holder.invalidate()
        logger.info("Rules cache cleared and engine networks invalidated")

    # Private Methods

    def _warn_if_streaming_misuse(self, engine: BaseEngine) -> None:
        """Log a one-time warning if a streaming engine is on the stateless path.

        Guardrail for proper use. The HTTP request/response path is **stateless**: each
        ``evaluate`` is independent and may be load-balanced across instances.
        A ``streaming_mode=True`` engine instead returns the **activation delta**
        keyed on the previous facts - repeated facts yield an empty
        ``fired_rules`` and the stream is order-dependent - so serving it here
        silently breaks the "every matching rule, every request" expectation.
        We surface it once (not per request) and point at the docs;
        ``engine.mode`` is also exposed in the stats payload so operators can see
        which contract is live.
        """
        if self._streaming_misuse_warned:
            return
        if getattr(engine, "mode", "stateless") == "streaming":
            self._streaming_misuse_warned = True
            logger.warning(
                "A streaming-mode engine is being served behind the stateless "
                "HTTP evaluate path. Streaming returns the ACTIVATION DELTA "
                "(repeated facts -> empty fired_rules) and is order-dependent, "
                "requiring sticky routing. For request/response scoring use a "
                "stateless engine (streaming_mode=False). See docs/sessions.md "
                "and docs/working-memory.md (Streaming semantics)."
            )

    def _get_rules(
        self,
        group: str | None = None,
        rule_ids: list[int] | None = None,
    ) -> list[dict[str, Any]]:
        """Get rules from cache or database.

        Args:
            group: Optional group filter
            rule_ids: Optional specific rule IDs

        Returns:
            List of rule dictionaries
        """
        if self._cache:
            return self._cache.get_rules(self._db, group)

        # Fallback: load from database
        return RuleCache._load_rules_from_db(self._db, group)

    def _collect_metrics(
        self, result: EvaluationResult, latency_ms: float, rules_count: int
    ) -> None:
        """Collect evaluation metrics.

        Args:
            result: Evaluation result
            latency_ms: Latency in milliseconds
            rules_count: Total rules evaluated
        """
        try:
            from fluxrules.utils.metrics import get_metrics

            metrics = get_metrics()
            metrics.observe_processing_time(latency_ms / 1000)
            metrics.increment_rules_fired(len(result.fired_rules))
            metrics.increment_events_processed()
        except Exception as e:
            logger.debug(f"Failed to collect metrics: {e}")

    def _format_response(self, result: EvaluationResult, latency_ms: float) -> dict[str, Any]:
        """Convert typed EvaluationResult to API dict format.

        Args:
            result: Typed evaluation result
            latency_ms: Latency in milliseconds

        Returns:
            Dictionary formatted for API response
        """
        return {
            "matched_rules": [
                {
                    "id": rule_id,
                    "name": f"rule_{rule_id}",
                    "priority": 0,
                }
                for rule_id in result.fired_rules
            ],
            "execution_order": result.fired_rules,
            "rules_by_domain": result.rules_by_domain,
            "rules_by_tag": result.rules_by_tag,
            "actions": result.actions,
            "explanations": result.explanations,
            "engine_type": self._engine_type,
            "stats": {
                "latency_ms": round(latency_ms, 2),
                "rules_evaluated": len(result.candidate_rule_ids),
                "rules_matched": len(result.fired_rules),
            },
        }
