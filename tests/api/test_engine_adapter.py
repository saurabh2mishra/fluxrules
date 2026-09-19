"""Tests for APIEngineAdapter."""

import pytest
from sqlalchemy.orm import Session

from fluxrules.api.engines import APIEngineAdapter, RuleCache


class TestAPIEngineAdapter:
    """Test APIEngineAdapter with different engine types."""

    def test_adapter_initialization_phreak(self, db_session: Session):
        """Test adapter initialization with PHREAK engine."""
        adapter = APIEngineAdapter(engine_type="PHREAK", db=db_session)
        assert adapter._engine_type == "PHREAK"
        assert adapter._engine is not None

    def test_adapter_initialization_rejects_rete(self, db_session: Session):
        """RETE is no longer a selectable engine and must be rejected."""
        with pytest.raises(ValueError, match="Invalid engine type"):
            APIEngineAdapter(engine_type="RETE", db=db_session)

    def test_adapter_initialization_rejects_interpreter(self, db_session: Session):
        """INTERPRETER is no longer a selectable engine and must be rejected."""
        with pytest.raises(ValueError, match="Invalid engine type"):
            APIEngineAdapter(engine_type="INTERPRETER", db=db_session)

    def test_adapter_invalid_engine_type(self, db_session: Session):
        """Test adapter with invalid engine type."""
        with pytest.raises(ValueError, match="Invalid engine type"):
            APIEngineAdapter(engine_type="INVALID", db=db_session)

    def test_adapter_caching_enabled(self, db_session: Session):
        """Test adapter with caching enabled."""
        adapter = APIEngineAdapter(engine_type="PHREAK", db=db_session, enable_cache=True)
        assert adapter._cache is not None

    def test_adapter_caching_disabled(self, db_session: Session):
        """Test adapter with caching disabled."""
        adapter = APIEngineAdapter(engine_type="PHREAK", db=db_session, enable_cache=False)
        assert adapter._cache is None

    def test_adapter_evaluate_basic(self, db_session: Session):
        """Test basic evaluation with adapter."""
        adapter = APIEngineAdapter(engine_type="PHREAK", db=db_session, enable_cache=True)
        result = adapter.evaluate(event={"amount": 100, "status": "active"}, rule_ids=None)

        # Check result structure
        assert "matched_rules" in result
        assert "execution_order" in result
        assert "actions" in result
        assert "explanations" in result
        assert "engine_type" in result
        assert "stats" in result
        assert result["engine_type"] == "PHREAK"

    def test_adapter_get_stats(self, db_session: Session):
        """Test getting engine stats through adapter."""
        adapter = APIEngineAdapter(engine_type="PHREAK", db=db_session)
        stats = adapter.get_stats()

        assert "engine_type" in stats
        assert stats["engine_type"] == "PHREAK"
        assert "caching_enabled" in stats

    def test_adapter_reload_rules(self, db_session: Session):
        """Test reloading rules through adapter."""
        adapter = APIEngineAdapter(engine_type="PHREAK", db=db_session, enable_cache=True)
        # Should not raise
        adapter.reload_rules()

    def test_rule_cache_initialization(self):
        """Test RuleCache initialization."""
        cache = RuleCache(enable_redis=False)
        assert cache is not None

    def test_rule_cache_get_rules_empty(self, db_session: Session):
        """Test getting rules from empty cache."""
        cache = RuleCache(enable_redis=False)
        rules = cache.get_rules(db_session)
        # Should return empty list or list of actual rules from db
        assert isinstance(rules, list)

    def test_rule_cache_clear(self):
        """Test clearing the cache."""
        cache = RuleCache(enable_redis=False)
        cache.clear()
        # Should not raise

    def test_adapter_response_format(self, db_session: Session):
        """Test that adapter returns correctly formatted response."""
        adapter = APIEngineAdapter(engine_type="PHREAK", db=db_session)
        result = adapter.evaluate(event={"test": True})

        # Verify response format
        assert isinstance(result, dict)
        assert "matched_rules" in result
        assert isinstance(result["matched_rules"], list)
        assert "stats" in result
        assert isinstance(result["stats"], dict)
        assert "latency_ms" in result["stats"]
        assert "rules_evaluated" in result["stats"]
        assert "rules_matched" in result["stats"]

    def test_adapter_db_persistence_phreak(self, db_session: Session):
        """Test PHREAK adapter correctly passes db for rule persistence."""
        adapter = APIEngineAdapter(engine_type="PHREAK", db=db_session, enable_cache=True)
        # Verify db is stored for rule loading
        assert adapter._db is db_session
        # Adapter should load rules from db during evaluate
        result = adapter.evaluate(event={"amount": 100})
        assert isinstance(result, dict)
        # Stats should show rules were evaluated
        assert "stats" in result

    def test_adapter_db_persistence_rete(self, db_session: Session):
        """Reject RETE at construction even when a db session is provided."""
        with pytest.raises(ValueError, match="Invalid engine type"):
            APIEngineAdapter(engine_type="RETE", db=db_session, enable_cache=True)

    def test_rule_cache_with_db_persistence(self, db_session: Session):
        """Test RuleCache loads rules from database for persistence."""
        cache = RuleCache(enable_redis=False)
        # Get rules should load from db when cache is empty
        rules = cache.get_rules(db_session)
        assert isinstance(rules, list)
        # Should have database connection working
        assert cache is not None

    def test_adapter_multiple_evaluations_with_db(self, db_session: Session):
        """Test adapter performs multiple evaluations with db persistence."""
        adapter = APIEngineAdapter(engine_type="PHREAK", db=db_session, enable_cache=True)
        # First evaluation
        result1 = adapter.evaluate(event={"amount": 100, "status": "active"})
        assert isinstance(result1, dict)

        # Second evaluation - should reuse cached rules from db
        result2 = adapter.evaluate(event={"amount": 200, "status": "inactive"})
        assert isinstance(result2, dict)

        # Both should have engine_type set
        assert result1["engine_type"] == "PHREAK"
        assert result2["engine_type"] == "PHREAK"

    def test_adapter_does_not_rebuild_network_per_request(self, db_session: Session):
        """P0.1: an unchanged rule set must be built once and reused.

        Regression guard for the per-request ``load_rules`` defect. With a stable
        rule set, repeated ``evaluate`` calls must reuse a single warm engine, so
        the holder's ``builds`` counter stays at (at most) 1.
        """
        adapter = APIEngineAdapter(engine_type="PHREAK", db=db_session, enable_cache=True)
        for amount in range(20):
            adapter.evaluate(event={"amount": amount})

        holder_stats = adapter.get_stats()["engine_holder"]
        assert holder_stats["builds"] <= 1, (
            f"network rebuilt {holder_stats['builds']} times for a stable rule set "
            "- per-request load_rules regression"
        )
        # Most requests reused the warm engine.
        assert holder_stats["hits"] >= 19

    def test_adapter_reload_invalidates_engine_cache(self, db_session: Session):
        """reload_rules must drop warm engines so the next request rebuilds."""
        adapter = APIEngineAdapter(engine_type="PHREAK", db=db_session, enable_cache=True)
        adapter.evaluate(event={"amount": 1})
        adapter.reload_rules()
        assert adapter.get_stats()["engine_holder"]["warm_engines"] == 0

    def test_adapter_stats_expose_rebuild_accounting(self, db_session: Session):
        """P2.4: holder stats expose rebuild count + build durations."""
        adapter = APIEngineAdapter(engine_type="PHREAK", db=db_session, enable_cache=True)
        adapter.evaluate(event={"amount": 1})
        holder = adapter.get_stats()["engine_holder"]
        for key in (
            "builds",
            "hits",
            "evictions",
            "reuse_rate",
            "last_build_seconds",
            "avg_build_seconds",
        ):
            assert key in holder

    def test_adapter_surfaces_observability_when_metrics_enabled(self, db_session: Session):
        """P2.4: with metrics on, get_stats exposes per-engine observability."""
        adapter = APIEngineAdapter(
            engine_type="PHREAK",
            db=db_session,
            enable_cache=True,
            enable_metrics=True,
        )
        for amount in range(10):
            adapter.evaluate(event={"amount": amount})

        stats = adapter.get_stats()
        assert stats["metrics_enabled"] is True
        assert "observability" in stats
        obs = stats["observability"]
        # Core P2.4 signals present.
        for key in (
            "mode",
            "alpha_prune_ratio",
            "candidates_per_fact_in",
            "working_memory_size",
            "engine_rebuilds",
        ):
            assert key in obs, key
        assert obs["mode"] == "stateless"

    def test_adapter_no_observability_when_metrics_disabled(self, db_session: Session):
        """Default (metrics off) must not attach the observability block."""
        adapter = APIEngineAdapter(
            engine_type="PHREAK",
            db=db_session,
            enable_cache=True,
            enable_metrics=False,
        )
        adapter.evaluate(event={"amount": 1})
        stats = adapter.get_stats()
        assert stats["metrics_enabled"] is False
        assert "observability" not in stats
