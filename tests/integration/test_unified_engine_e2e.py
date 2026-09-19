"""End-to-end integration tests for the unified engine."""

from __future__ import annotations

import pytest

from fluxrules import Rule
from fluxrules.engine.phreak import PhreakEngine


def _rule(rid, field, op, value, domain="default", tags=None, priority=0, action=""):
    return Rule(
        id=rid,
        name=f"rule_{rid}",
        condition_dsl={"type": "condition", "field": field, "op": op, "value": value},
        action=action,
        priority=priority,
        domain=domain,
        tags=frozenset(tags or []),
        persist=False,
    )


def _composite(rid, conditions, logic="AND", domain="default", tags=None, priority=0, action=""):
    return Rule(
        id=rid,
        name=f"rule_{rid}",
        condition_dsl={
            "type": "composite",
            "logic": logic,
            "conditions": [
                {"type": "condition", "field": f, "op": o, "value": v} for f, o, v in conditions
            ],
        },
        action=action,
        priority=priority,
        domain=domain,
        tags=frozenset(tags or []),
        persist=False,
    )


@pytest.fixture(params=["phreak"])
def engine(request):
    return PhreakEngine()


class TestFraudDetectionWorkflow:
    """Load fraud + compliance rules, evaluate transaction."""

    def test_fraud_and_compliance(self, engine):
        engine.load_rules(
            [
                _rule(
                    1,
                    "amount",
                    ">",
                    10000,
                    domain="fraud_detection",
                    tags=["high_value"],
                    priority=5,
                    action="flag_fraud",
                ),
                _composite(
                    2,
                    [("amount", ">", 5000), ("country", "==", "NG")],
                    domain="compliance",
                    tags=["high_risk_country"],
                    priority=3,
                    action="compliance_review",
                ),
                _rule(
                    3,
                    "amount",
                    ">",
                    50000,
                    domain="aml",
                    tags=["large_transaction"],
                    priority=2,
                    action="aml_alert",
                ),
            ]
        )
        transaction = {"amount": 15000, "country": "NG"}
        result = engine.evaluate(transaction)

        assert 1 in result.fired_rules  # fraud: amount > 10000
        assert 2 in result.fired_rules  # compliance: amount > 5000 AND country == NG
        assert 3 not in result.fired_rules  # aml: amount not > 50000

        assert "fraud_detection" in result.rules_by_domain
        assert "compliance" in result.rules_by_domain
        assert "flag_fraud" in result.actions
        assert "compliance_review" in result.actions


class TestCrossDomainEvaluation:
    """Single fact triggers fraud, compliance, AND loan rules."""

    def test_single_fact_multiple_domains(self, engine):
        engine.load_rules(
            [
                _rule(1, "amount", ">", 1000, domain="fraud"),
                _rule(2, "amount", ">", 500, domain="loan"),
                _rule(3, "amount", ">", 2000, domain="compliance"),
            ]
        )
        result = engine.evaluate({"amount": 3000})
        assert set(result.fired_rules) == {1, 2, 3}
        assert len(result.rules_by_domain) == 3


class TestMultiFactSession:
    """Multi-step fact addition and evaluation."""

    def test_stateful_facts(self, engine):
        engine.load_rules([_rule(1, "amount", ">", 100)])
        fid1 = engine.assert_fact({"amount": 500})
        fid2 = engine.assert_fact({"amount": 50})

        assert engine.working_memory.get_fact(fid1) is not None
        assert engine.working_memory.get_fact(fid2) is not None

        engine.retract_fact(fid2)
        assert engine.working_memory.get_fact(fid2) is None


class TestFilteredEvaluation:
    """Filtered evaluation across domains and tags."""

    def test_domain_filter_isolation(self, engine):
        engine.load_rules(
            [
                _rule(1, "amount", ">", 100, domain="fraud", action="a1"),
                _rule(2, "amount", ">", 100, domain="loan", action="a2"),
                _rule(3, "amount", ">", 100, domain="compliance", action="a3"),
            ]
        )
        result = engine.evaluate_by_domain({"amount": 500}, domains=["fraud"])
        assert result.fired_rules == [1]
        assert result.actions == ["a1"]

    def test_tag_filter(self, engine):
        engine.load_rules(
            [
                _rule(1, "amount", ">", 100, tags=["high_value"]),
                _rule(2, "amount", ">", 100, tags=["low_value"]),
            ]
        )
        result = engine.evaluate_by_tags({"amount": 500}, tags=["high_value"])
        assert result.fired_rules == [1]


class TestEngineFactory:
    """Ensure unified engines can be created via factory."""

    def test_factory_unified_phreak(self):
        from fluxrules.engine import get_engine

        e = get_engine(engine_type="PHREAK")
        assert isinstance(e, PhreakEngine)

    def test_factory_rejects_rete(self):
        import pytest

        from fluxrules.engine import get_engine

        with pytest.raises(ValueError, match="Unknown engine type"):
            get_engine(engine_type="RETE")

    def test_available_engines_includes_unified(self):
        from fluxrules.engine import get_available_engines

        available = get_available_engines()
        assert "PHREAK" in available
        assert "RETE" not in available


class TestHighRuleCount:
    """Test with larger rule sets to verify scalability."""

    def test_1k_rules(self, engine):
        rules = [
            _rule(i, "amount", ">", i, domain=f"domain_{i % 10}", priority=i % 5)
            for i in range(1000)
        ]
        engine.load_rules(rules)
        result = engine.evaluate({"amount": 500})
        assert len(result.fired_rules) > 0
        assert result.latency_ms < 5000  # should be fast
