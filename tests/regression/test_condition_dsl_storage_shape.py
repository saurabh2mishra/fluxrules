"""``rules.condition_dsl`` is a JSON column and must hold a JSON object.

The API service used to ``json.dumps`` the DSL before assigning it. Because
the column is ``JSON``, SQLAlchemy then serialised that string *again*: the
row held a JSON string whose content was JSON, and reading it back gave
``str`` rather than ``dict``.

Nothing failed. Every reader in the routes layer already carried an
``isinstance(x, str)`` guard and quietly decoded, so the round trip looked
correct end to end and the API tests passed with the bug present. The only
place the difference is visible is the stored column itself, which is what
these tests assert on.

``rule_versions`` and ``conflicted_rules`` hold the same DSL in ``Text``
columns, where ``json.dumps`` is correct. The distinction is the point: the
rule is not "never serialise", it is "serialise iff the column is Text".
"""

from __future__ import annotations

import json
import os
import tempfile

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from fluxrules.api.database import Base
from fluxrules.api.models.rule import Rule, RuleVersion

DSL = {
    "type": "or",
    "children": [
        {"type": "condition", "field": "amount", "op": "gt", "value": 100},
        {"type": "condition", "field": "region", "op": "eq", "value": "EU"},
    ],
}


@pytest.fixture()
def session():
    path = tempfile.mktemp(suffix=".db")
    engine = create_engine(f"sqlite:///{path}")
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()
    try:
        yield db
    finally:
        db.close()
        engine.dispose()
        if os.path.exists(path):
            os.unlink(path)


@pytest.fixture()
def service(session):
    """A ``RuleService`` bound to the throwaway session, with audit stubbed."""
    from unittest.mock import MagicMock

    from fluxrules.api.services.rule_service import RuleService

    svc = RuleService(session)
    svc.audit_service = MagicMock()
    return svc


def _stored_json_type(session) -> str:
    """The SQLite-level type of the stored value: 'object' or 'text'."""
    return session.execute(text("select json_type(condition_dsl) from rules")).scalar()


def test_rules_column_stores_a_json_object(session):
    """A dict assigned to the JSON column stays an object in the database."""
    session.add(Rule(name="r", condition_dsl=DSL, action="noop", enabled=True))
    session.commit()

    assert _stored_json_type(session) == "object"


def test_pre_serialising_the_dsl_double_encodes_it(session):
    """Pin the failure mode, so the fix cannot be silently reverted.

    This is what ``create_rule`` used to do. It is stored as ``text``, not
    ``object`` - the row is a JSON string containing JSON.
    """
    session.add(Rule(name="r", condition_dsl=json.dumps(DSL), action="noop", enabled=True))
    session.commit()

    assert _stored_json_type(session) == "text"


def test_dsl_round_trips_as_a_dict(session):
    """The value read back is the dict that went in, not a string of it."""
    rule = Rule(name="r", condition_dsl=DSL, action="noop", enabled=True)
    session.add(rule)
    session.commit()
    session.refresh(rule)

    assert isinstance(rule.condition_dsl, dict)
    assert rule.condition_dsl == DSL


def test_boolean_structure_survives_storage(session):
    """An ``or`` tree is still an ``or`` tree after a round trip.

    The wider failure this suite guards against is boolean structure being
    flattened to a conjunction somewhere in the pipeline.
    """
    rule = Rule(name="r", condition_dsl=DSL, action="noop", enabled=True)
    session.add(rule)
    session.commit()
    session.refresh(rule)

    assert rule.condition_dsl["type"] == "or"
    assert len(rule.condition_dsl["children"]) == 2


def test_version_snapshot_is_serialised_because_that_column_is_text(session):
    """``rule_versions.condition_dsl`` is Text, so it holds a JSON string.

    ``_create_version`` copies the value across a column-type boundary. Once
    ``rules`` holds a dict, that copy has to be serialised or the Text column
    receives a dict.
    """
    rule = Rule(name="r", condition_dsl=DSL, action="noop", enabled=True)
    session.add(rule)
    session.commit()
    session.refresh(rule)

    version = RuleVersion(
        rule_id=rule.id,
        version=1,
        name=rule.name,
        condition_dsl=json.dumps(rule.condition_dsl),
        action=rule.action,
        enabled=True,
    )
    session.add(version)
    session.commit()
    session.refresh(version)

    assert isinstance(version.condition_dsl, str)
    assert json.loads(version.condition_dsl) == DSL


class TestRuleServiceWritesAnObject:
    """The service is where the double-encode lived, so exercise it directly.

    Asserting on the ORM alone is not enough: a test that constructs ``Rule``
    itself passes whether or not ``create_rule`` serialises, because it never
    calls ``create_rule``. These tests go through the service and then read the
    raw column.
    """

    def test_create_rule_stores_an_object(self, session, service):
        from fluxrules.api.schemas.rule import RuleCreate

        service.create_rule(
            RuleCreate(name="created", condition_dsl=DSL, action="noop"),
            user_id=1,
        )

        assert _stored_json_type(session) == "object"

    def test_created_rule_reads_back_as_a_dict(self, session, service):
        from fluxrules.api.schemas.rule import RuleCreate

        rule = service.create_rule(
            RuleCreate(name="created", condition_dsl=DSL, action="noop"),
            user_id=1,
        )
        session.refresh(rule)

        assert isinstance(rule.condition_dsl, dict)
        assert rule.condition_dsl == DSL

    def test_update_rule_stores_an_object(self, session, service):
        from fluxrules.api.schemas.rule import RuleCreate, RuleUpdate

        rule = service.create_rule(
            RuleCreate(name="created", condition_dsl=DSL, action="noop"),
            user_id=1,
        )

        new_dsl = {
            "type": "and",
            "children": [{"type": "condition", "field": "x", "op": "eq", "value": 1}],
        }
        service.update_rule(rule.id, RuleUpdate(condition_dsl=new_dsl), user_id=1)
        session.refresh(rule)

        assert _stored_json_type(session) == "object"
        assert rule.condition_dsl == new_dsl

    def test_version_snapshot_survives_the_service_path(self, session, service):
        """``_create_version`` copies into a Text column and must serialise."""
        from fluxrules.api.schemas.rule import RuleCreate

        rule = service.create_rule(
            RuleCreate(name="created", condition_dsl=DSL, action="noop"),
            user_id=1,
        )

        version = session.query(RuleVersion).filter(RuleVersion.rule_id == rule.id).first()
        assert version is not None
        assert isinstance(version.condition_dsl, str)
        assert json.loads(version.condition_dsl) == DSL


class TestRuleMetadataHasTheSameSplit:
    """``rule_metadata`` is JSON on ``rules`` and Text on ``rule_versions``.

    Identical to ``condition_dsl``, and it carried the identical bug. It is
    tested separately because the two columns are easy to fix independently
    and be left inconsistent.
    """

    META = {"owner": "risk", "tags": ["a", "b"]}

    def test_create_rule_stores_metadata_as_an_object(self, session, service):
        from fluxrules.api.schemas.rule import RuleCreate

        service.create_rule(
            RuleCreate(name="m", condition_dsl=DSL, action="noop", rule_metadata=self.META),
            user_id=1,
        )

        stored = session.execute(text("select json_type(rule_metadata) from rules")).scalar()
        assert stored == "object"

    def test_metadata_reads_back_as_a_dict(self, session, service):
        from fluxrules.api.schemas.rule import RuleCreate

        rule = service.create_rule(
            RuleCreate(name="m", condition_dsl=DSL, action="noop", rule_metadata=self.META),
            user_id=1,
        )
        session.refresh(rule)

        assert isinstance(rule.rule_metadata, dict)
        assert rule.rule_metadata == self.META

    def test_update_stores_metadata_as_an_object(self, session, service):
        from fluxrules.api.schemas.rule import RuleCreate, RuleUpdate

        rule = service.create_rule(
            RuleCreate(name="m", condition_dsl=DSL, action="noop"),
            user_id=1,
        )
        service.update_rule(rule.id, RuleUpdate(rule_metadata=self.META), user_id=1)
        session.refresh(rule)

        stored = session.execute(text("select json_type(rule_metadata) from rules")).scalar()
        assert stored == "object"
        assert rule.rule_metadata == self.META

    def test_version_snapshot_serialises_metadata(self, session, service):
        from fluxrules.api.schemas.rule import RuleCreate

        rule = service.create_rule(
            RuleCreate(name="m", condition_dsl=DSL, action="noop", rule_metadata=self.META),
            user_id=1,
        )

        version = session.query(RuleVersion).filter(RuleVersion.rule_id == rule.id).first()
        assert isinstance(version.rule_metadata, str)
        assert json.loads(version.rule_metadata) == self.META

    def test_absent_metadata_stays_null(self, session, service):
        """``None`` must not become the string ``"null"``."""
        from fluxrules.api.schemas.rule import RuleCreate

        rule = service.create_rule(
            RuleCreate(name="m", condition_dsl=DSL, action="noop"),
            user_id=1,
        )
        session.refresh(rule)

        assert rule.rule_metadata is None
        version = session.query(RuleVersion).filter(RuleVersion.rule_id == rule.id).first()
        assert version.rule_metadata is None
