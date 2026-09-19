"""Tests for RuleService with persistence enabled."""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from fluxrules.api.database import Base
from fluxrules.api.models.rule import Rule as OrmRule  # noqa: F401 - registers table
from fluxrules.domain.models import EngineRule, RuleCondition, Ruleset
from fluxrules.services.rule_service import RuleService


@pytest.fixture()
def db_session():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()
    Base.metadata.drop_all(bind=engine)


def _make_ruleset(group="test"):
    return Ruleset(
        group=group,
        rules=(
            EngineRule(
                id=1,
                name="r1",
                conditions=(RuleCondition(fact="age", operator="gt", value=18),),
                actions=("allow",),
                priority=1,
                group=group,
            ),
            EngineRule(
                id=2,
                name="r2",
                conditions=(RuleCondition(fact="status", operator="eq", value="active"),),
                actions=("notify",),
                priority=2,
                group=group,
            ),
        ),
    )


class TestInMemoryBackwardCompatibility:
    """Existing in-memory behaviour must not break."""

    def test_default_no_args(self):
        RuleService._reset()
        s = RuleService()
        rs = _make_ruleset()
        s.persist(rs)
        assert s.get_ruleset(rs.group) is rs

    def test_evaluate_works(self):
        s = RuleService()
        rs = _make_ruleset()
        s.persist(rs)
        result = s.evaluate_ruleset(rs.group, {"age": 25, "status": "active"})
        assert len(result.matched_rule_ids) > 0

    def test_create_returns_fresh_instances(self):
        a = RuleService.create()
        b = RuleService.create()
        assert a is not b


class TestWithPersistence:
    def test_with_persistence_factory(self, db_session):
        s = RuleService.with_persistence(db_session)
        assert s._persistence_enabled is True
        assert s._repository is not None

    def test_save_and_reload(self, db_session):
        s1 = RuleService.with_persistence(db_session)
        rs = _make_ruleset("persist")
        s1.persist(rs)

        # Create a new service from same session - rules should load from DB
        s2 = RuleService.with_persistence(db_session)
        loaded = s2.get_ruleset_by_name("persist")
        assert len(loaded.rules) == 2

    def test_evaluate_persisted(self, db_session):
        s = RuleService.with_persistence(db_session)
        rs = _make_ruleset("eval")
        s.persist(rs)
        result = s.evaluate_ruleset(rs.group, {"age": 25, "status": "inactive"})
        assert "allow" in result.actions

    def test_explain(self, db_session):
        s = RuleService.with_persistence(db_session)
        rs = _make_ruleset("expl")
        s.persist(rs)
        result = s.evaluate_ruleset(rs.group, {"age": 25})
        explained = s.explain(result.execution_id)
        assert explained.execution_id == result.execution_id
