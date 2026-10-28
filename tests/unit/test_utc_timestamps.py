"""Timestamp and small helper paths touched by the Python 3.11 (datetime.UTC) migration."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock

import jwt
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from fluxrules.adapters.persistence.sqlalchemy_adapter import SQLAlchemyPersistenceAdapter
from fluxrules.api.config import settings
from fluxrules.api.database import Base
from fluxrules.api.engines.adapter import RuleCache
from fluxrules.api.services.auth_service import create_access_token, get_secret_key
from fluxrules.domain.models import EngineRule, RuleCondition
from fluxrules.domain.rule_builder import RuleBuilder
from fluxrules.plugins.discovery import _iter_entry_points
from fluxrules.services.execution.session_context import SessionContext


def _decoded_exp(token: str) -> datetime:
    payload = jwt.decode(token, get_secret_key(), algorithms=[settings.ALGORITHM])
    return datetime.fromtimestamp(payload["exp"], tz=UTC)


class TestCreateAccessToken:
    def test_default_expiry_is_fifteen_minutes(self):
        before = datetime.now(UTC)
        exp = _decoded_exp(create_access_token({"sub": "alice"}))
        assert timedelta(minutes=14) < exp - before <= timedelta(minutes=15, seconds=5)

    def test_custom_expiry(self):
        before = datetime.now(UTC)
        exp = _decoded_exp(create_access_token({"sub": "alice"}, timedelta(hours=2)))
        assert timedelta(hours=1, minutes=59) < exp - before <= timedelta(hours=2, seconds=5)


class TestRuleBuilderApproval:
    def test_approval_date_defaults_to_now_utc(self):
        before = datetime.now(UTC)
        builder = RuleBuilder("approved").approved_by("reviewer")
        assert builder._approval_date.tzinfo is UTC
        assert before <= builder._approval_date <= datetime.now(UTC)

    def test_explicit_approval_date_is_kept(self):
        when = datetime(2026, 1, 2, tzinfo=UTC)
        assert RuleBuilder("approved").approved_by("reviewer", when)._approval_date == when


class TestSessionContextTimezone:
    def test_naive_created_at_is_treated_as_utc(self):
        ctx = SessionContext(
            session_id="s1", group="g", created_at=datetime(2026, 1, 1), ttl_seconds=60
        )
        assert ctx.created_at.tzinfo is UTC

    def test_is_expired_compares_against_utc_now(self):
        fresh = SessionContext(
            session_id="s1", group="g", created_at=datetime.now(UTC), ttl_seconds=60
        )
        stale = SessionContext(
            session_id="s2",
            group="g",
            created_at=datetime.now(UTC) - timedelta(seconds=120),
            ttl_seconds=60,
        )
        assert not fresh.is_expired()
        assert stale.is_expired()


class TestSQLAlchemyAdapterUpdate:
    def test_update_rule_sets_updated_at(self):
        engine = create_engine(
            "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
        )
        Base.metadata.create_all(bind=engine)
        db = sessionmaker(bind=engine)()
        try:
            adapter = SQLAlchemyPersistenceAdapter(db=db)
            rule_id = adapter.save_rule(
                EngineRule(
                    id=None,
                    name="before",
                    condition_nodes=(RuleCondition(fact="amount", operator=">", value=1),),
                    actions=("flag",),
                    priority=1,
                )
            )
            before = datetime.now(UTC).replace(tzinfo=None)
            updated = adapter.update_rule(rule_id, name="after", actions=["a", "b"])

            assert updated is not None
            assert updated.name == "after"
            from fluxrules.api.models.rule import Rule as OrmRule

            orm_rule = db.query(OrmRule).filter(OrmRule.id == rule_id).one()
            assert orm_rule.action == "a\nb"
            assert orm_rule.updated_at.replace(tzinfo=None) >= before
        finally:
            db.close()
            Base.metadata.drop_all(bind=engine)


class TestRuleCacheRedisWrite:
    def test_update_redis_cache_writes_json_with_ttl(self):
        cache = RuleCache(enable_redis=False)
        cache._redis = MagicMock()
        cache._redis_available = True
        rules = [{"id": 1, "name": "r1"}]

        cache._update_redis_cache("rules:all", rules)

        cache._redis.set.assert_called_once_with(
            "rule_engine:rules:all", json.dumps(rules), ex=RuleCache.CACHE_TTL
        )


class TestIterEntryPoints:
    def test_returns_registered_entry_points(self):
        names = {ep.name for ep in _iter_entry_points("console_scripts")}
        assert "fluxrules" in names

    def test_unknown_group_is_empty(self):
        assert _iter_entry_points("fluxrules.no_such_group") == []
