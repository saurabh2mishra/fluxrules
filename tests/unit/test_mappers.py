"""Tests for persistence mappers (domain ↔ ORM conversions)."""

from __future__ import annotations

from datetime import datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from fluxrules.api.database import Base
from fluxrules.domain.models import EngineRule, RuleCondition


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


class TestDomainRuleToOrm:
    def test_basic_conversion(self):
        from fluxrules.persistence.mappers import domain_rule_to_orm

        rule = EngineRule(
            id=0,
            name="TestRule",
            conditions=(RuleCondition(fact="age", operator="gt", value=18),),
            actions=("allow",),
            priority=5,
            group="access",
            description="Age check",
            enabled=True,
        )
        orm = domain_rule_to_orm(rule, group="access")
        assert orm.name == "TestRule"
        assert orm.group == "access"
        assert orm.priority == 5
        assert orm.enabled is True
        assert orm.action == "allow"
        # The column holds a DSL dict, never a list of condition dicts: one
        # stored shape means readers never have to guess which they have.
        assert orm.condition_dsl == {
            "type": "condition",
            "field": "age",
            "op": "gt",
            "value": 18,
        }

    def test_multiple_actions(self):
        from fluxrules.persistence.mappers import domain_rule_to_orm

        rule = EngineRule(
            id=0,
            name="Multi",
            conditions=(RuleCondition(fact="x", operator="eq", value=1),),
            actions=("a1", "a2", "a3"),
        )
        orm = domain_rule_to_orm(rule)
        assert orm.action == "a1\na2\na3"

    def test_empty_actions(self):
        from fluxrules.persistence.mappers import domain_rule_to_orm

        rule = EngineRule(
            id=0,
            name="NoAction",
            conditions=(RuleCondition(fact="x", operator="eq", value=1),),
        )
        orm = domain_rule_to_orm(rule)
        assert orm.action == ""

    def test_canonical_rule_stores_condition_dsl(self):
        """A canonical Pydantic Rule is stored via its condition_dsl, not conditions."""
        from fluxrules.domain.unified_rule import Rule as CanonicalRule
        from fluxrules.persistence.mappers import domain_rule_to_orm

        rule = CanonicalRule(
            id=1,
            name="Canonical",
            condition_dsl={"type": "condition", "field": "x", "op": ">", "value": 0},
            action="flag",
            domain="fraud",
        )
        orm = domain_rule_to_orm(rule)
        assert orm.name == "Canonical"
        assert orm.action == "flag"
        assert orm.group == "fraud"
        assert orm.condition_dsl == {
            "type": "condition",
            "field": "x",
            "op": ">",
            "value": 0,
        }


class TestOrmRuleToDomain:
    def test_round_trip(self, db_session):
        from fluxrules.api.models.rule import Rule as OrmRule
        from fluxrules.persistence.mappers import orm_rule_to_domain

        orm = OrmRule(
            name="RoundTrip",
            description="Desc",
            group="grp",
            priority=10,
            enabled=True,
            condition_dsl={
                "type": "and",
                "children": [
                    {"type": "condition", "field": "age", "op": "gte", "value": 21},
                    {
                        "type": "condition",
                        "field": "status",
                        "op": "eq",
                        "value": "active",
                    },
                ],
            },
            action="grant\nnotify",
            created_at=datetime(2026, 1, 1, 12, 0, 0),
            updated_at=datetime(2026, 1, 2, 12, 0, 0),
        )
        db_session.add(orm)
        db_session.commit()
        db_session.refresh(orm)

        domain = orm_rule_to_domain(orm)
        assert isinstance(domain.id, int)
        assert domain.name == "RoundTrip"
        assert domain.group == "grp"
        assert domain.priority == 10
        assert len(domain.conditions) == 2
        assert domain.conditions[0].fact == "age"
        assert domain.actions == ("grant", "notify")
        assert domain.created_at == "2026-01-01T12:00:00"
        assert domain.updated_at == "2026-01-02T12:00:00"

    def test_rule_id_is_integer(self, db_session):
        from fluxrules.api.models.rule import Rule as OrmRule
        from fluxrules.persistence.mappers import orm_rule_to_domain

        orm = OrmRule(
            name="IntId",
            condition_dsl={"type": "and", "children": []},
            action="",
        )
        db_session.add(orm)
        db_session.commit()
        db_session.refresh(orm)

        domain = orm_rule_to_domain(orm)
        assert isinstance(domain.id, int)

    def test_rule_name_exists(self, db_session):
        from fluxrules.api.models.rule import Rule as OrmRule
        from fluxrules.persistence.mappers import orm_rule_to_domain

        orm = OrmRule(
            name="MyRuleName",
            condition_dsl={"type": "and", "children": []},
            action="",
        )
        db_session.add(orm)
        db_session.commit()
        db_session.refresh(orm)

        domain = orm_rule_to_domain(orm)
        assert domain.name == "MyRuleName"
        assert hasattr(domain, "name")

    def test_timestamps_are_strings(self, db_session):
        from fluxrules.api.models.rule import Rule as OrmRule
        from fluxrules.persistence.mappers import orm_rule_to_domain

        orm = OrmRule(
            name="Ts",
            condition_dsl={"type": "and", "children": []},
            action="",
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
        db_session.add(orm)
        db_session.commit()
        db_session.refresh(orm)

        domain = orm_rule_to_domain(orm)
        assert isinstance(domain.created_at, str)
        assert isinstance(domain.updated_at, str)

    def test_all_operators(self):
        from fluxrules.persistence.mappers import domain_rule_to_orm, orm_rule_to_domain

        operators = [
            "eq",
            "ne",
            "gt",
            "gte",
            "lt",
            "lte",
            "contains",
            "not_contains",
            "in",
            "not_in",
        ]
        for op in operators:
            rule = EngineRule(
                id=0,
                name=f"op_{op}",
                conditions=(RuleCondition(fact="x", operator=op, value=1),),
            )
            orm = domain_rule_to_orm(rule)
            assert orm.condition_dsl["op"] == op
            # And it survives the trip back, which is the point of storing it.
            assert orm_rule_to_domain(orm).conditions[0].operator == op
