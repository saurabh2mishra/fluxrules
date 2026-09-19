"""Tests for RuleRepository."""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from fluxrules.api.database import Base
from fluxrules.api.models.rule import Rule as OrmRule  # noqa: F401 - registers table
from fluxrules.domain.models import EngineRule, RuleCondition, Ruleset
from fluxrules.persistence.rule_repository import RuleRepository


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


@pytest.fixture()
def repo(db_session):
    return RuleRepository(db_session)


def _make_rule(name="test", group="grp", priority=0, **kw):
    return EngineRule(
        id=0,
        name=name,
        conditions=(RuleCondition(fact="age", operator="gt", value=18),),
        actions=("allow",),
        priority=priority,
        group=group,
        description="desc",
        enabled=True,
        **kw,
    )


class TestSaveAndLoad:
    def test_save_and_load_single(self, repo):
        rule = _make_rule("r1")
        rid = repo.save_rule(rule, group="grp")
        assert isinstance(rid, int)

        loaded = repo.load_rule(rid)
        assert loaded is not None
        assert loaded.id == rid
        assert loaded.name == "r1"
        assert loaded.group == "grp"
        assert loaded.conditions[0].fact == "age"
        assert loaded.actions == ("allow",)

    def test_load_nonexistent(self, repo):
        assert repo.load_rule(9999) is None

    def test_save_multiple_load_by_group(self, repo):
        repo.save_rule(_make_rule("a", group="g1"), group="g1")
        repo.save_rule(_make_rule("b", group="g1"), group="g1")
        repo.save_rule(_make_rule("c", group="g2"), group="g2")

        g1 = repo.load_rules_by_group("g1")
        assert len(g1) == 2
        g2 = repo.load_rules_by_group("g2")
        assert len(g2) == 1

    def test_load_all(self, repo):
        repo.save_rule(_make_rule("x"))
        repo.save_rule(_make_rule("y"))
        all_rules = repo.load_all_rules()
        assert len(all_rules) == 2

    def test_load_ruleset(self, repo):
        repo.save_rule(_make_rule("a", group="rs1"), group="rs1")
        repo.save_rule(_make_rule("b", group="rs1"), group="rs1")
        rs = repo.load_ruleset("rs1")
        assert isinstance(rs, Ruleset)
        assert rs.group == "rs1"
        assert len(rs.rules) == 2

    def test_save_ruleset(self, repo):
        ruleset = Ruleset(
            group="bulk",
            rules=(
                _make_rule("r1", group="bulk"),
                _make_rule("r2", group="bulk"),
            ),
        )
        ids = repo.save_ruleset(ruleset)
        assert len(ids) == 2
        loaded = repo.load_ruleset("bulk")
        assert len(loaded.rules) == 2

    def test_load_all_rulesets(self, repo):
        repo.save_rule(_make_rule("a", group="g1"), group="g1")
        repo.save_rule(_make_rule("b", group="g2"), group="g2")
        rulesets = repo.load_all_rulesets()
        assert "g1" in rulesets
        assert "g2" in rulesets


class TestUpdateDelete:
    def test_update_rule(self, repo):
        rid = repo.save_rule(_make_rule("orig"))
        updated = repo.update_rule(rid, name="updated", priority=99)
        assert updated is not None
        assert updated.name == "updated"
        assert updated.priority == 99

    def test_update_nonexistent(self, repo):
        assert repo.update_rule(9999, name="x") is None

    def test_delete_rule(self, repo):
        rid = repo.save_rule(_make_rule("del"))
        assert repo.delete_rule(rid) is True
        assert repo.load_rule(rid) is None

    def test_delete_nonexistent(self, repo):
        assert repo.delete_rule(9999) is False


class TestDataIntegrity:
    def test_matched_rule_ids_are_integers(self, repo):
        from fluxrules.domain.models import EvaluationResult

        result = EvaluationResult(
            execution_id="e1",
            ruleset_group="test",
            matched_rule_ids=[1, 2, 3],
            actions=["a"],
        )
        assert all(isinstance(rid, int) for rid in result.matched_rule_ids)

    def test_conditions_round_trip(self, repo):
        rule = EngineRule(
            id=0,
            name="conds",
            conditions=(
                RuleCondition(fact="x", operator="eq", value="hello"),
                RuleCondition(fact="y", operator="gt", value=42),
                RuleCondition(fact="z", operator="contains", value="abc"),
            ),
            actions=("act1", "act2"),
        )
        rid = repo.save_rule(rule)
        loaded = repo.load_rule(rid)
        assert len(loaded.conditions) == 3
        assert loaded.conditions[0].value == "hello"
        assert loaded.conditions[1].value == 42
        assert loaded.actions == ("act1", "act2")
