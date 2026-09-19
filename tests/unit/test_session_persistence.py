"""Tests for EvaluationSession save / restore (Feature 2)."""

from __future__ import annotations

import json

import pytest

from fluxrules.domain.models import EngineRule, RuleCondition, Ruleset
from fluxrules.services.rule_service import RuleService
from fluxrules.services.session import EvaluationSession, SessionSnapshot


@pytest.fixture()
def service() -> RuleService:
    svc = RuleService()
    ruleset = Ruleset(
        group="test_rules",
        rules=(
            EngineRule(
                id=1,
                name="High value",
                priority=10,
                group="test_rules",
                conditions=(RuleCondition(fact="amount", operator="gt", value=100),),
                actions=("flag:review",),
            ),
        ),
    )
    svc.persist(ruleset)
    return svc


class TestCreateSession:
    def test_returns_evaluation_session(self, service: RuleService):
        session = service.create_session("test_rules")
        assert isinstance(session, EvaluationSession)
        assert session.ruleset_id == "test_rules"

    def test_session_has_unique_execution_id(self, service: RuleService):
        s1 = service.create_session("test_rules")
        s2 = service.create_session("test_rules")
        assert s1.execution_id != s2.execution_id


class TestAddFact:
    def test_add_fact(self, service: RuleService):
        session = service.create_session("test_rules")
        session.add_fact("age", 30)
        assert session.facts["age"] == 30

    def test_add_facts_bulk(self, service: RuleService):
        session = service.create_session("test_rules")
        session.add_facts({"a": 1, "b": 2})
        assert session.facts == {"a": 1, "b": 2}

    def test_remove_fact(self, service: RuleService):
        session = service.create_session("test_rules")
        session.add_fact("x", 1)
        session.remove_fact("x")
        assert "x" not in session.facts

    def test_clear_facts(self, service: RuleService):
        session = service.create_session("test_rules")
        session.add_facts({"a": 1, "b": 2})
        session.clear_facts()
        assert session.facts == {}


class TestEvaluate:
    def test_evaluate_returns_result(self, service: RuleService):
        session = service.create_session("test_rules")
        session.add_fact("amount", 200)
        result = session.evaluate()
        assert result is not None
        assert len(result.matched_rule_ids) >= 1

    def test_evaluate_stores_result(self, service: RuleService):
        session = service.create_session("test_rules")
        session.add_fact("amount", 200)
        result = session.evaluate()
        assert session.result is result


class TestSaveRestore:
    def test_save_returns_json(self, service: RuleService):
        session = service.create_session("test_rules")
        session.add_fact("value", 100)
        snapshot_json = session.save()
        assert isinstance(snapshot_json, str)
        data = json.loads(snapshot_json)
        assert data["ruleset_id"] == "test_rules"
        assert data["facts"]["value"] == 100
        assert "execution_id" in data
        assert "timestamp" in data

    def test_restore_reconstructs_session(self, service: RuleService):
        session1 = service.create_session("test_rules")
        session1.add_fact("value", 100)
        snapshot = session1.save()

        session2 = EvaluationSession.restore(snapshot, service)
        assert session2.ruleset_id == "test_rules"
        assert session2.facts["value"] == 100
        assert session2.execution_id == session1.execution_id

    def test_restore_and_evaluate(self, service: RuleService):
        session1 = service.create_session("test_rules")
        session1.add_fact("amount", 200)
        snapshot = session1.save()

        session2 = EvaluationSession.restore(snapshot, service)
        result = session2.evaluate()
        assert result is not None
        assert len(result.matched_rule_ids) >= 1

    def test_restore_add_more_facts_and_evaluate(self, service: RuleService):
        session1 = service.create_session("test_rules")
        session1.add_fact("amount", 50)
        snapshot = session1.save()

        session2 = EvaluationSession.restore(snapshot, service)
        session2.add_fact("amount", 200)
        result = session2.evaluate()
        assert len(result.matched_rule_ids) >= 1


class TestSessionSnapshot:
    def test_roundtrip(self):
        snap = SessionSnapshot(
            execution_id="abc",
            ruleset_id="test_rules",
            facts={"x": 1},
            timestamp="2026-01-01T00:00:00+00:00",
        )
        j = snap.to_json()
        snap2 = SessionSnapshot.from_json(j)
        assert snap2.execution_id == "abc"
        assert snap2.facts == {"x": 1}

    def test_metadata_preserved(self):
        snap = SessionSnapshot(
            execution_id="abc",
            ruleset_id="test_rules",
            facts={},
            timestamp="now",
            metadata={"env": "test"},
        )
        snap2 = SessionSnapshot.from_json(snap.to_json())
        assert snap2.metadata == {"env": "test"}
