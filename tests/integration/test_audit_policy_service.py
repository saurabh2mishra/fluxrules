"""Tests for AuditPolicyService (Feature 3) - CRUD, run, scheduler."""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from fluxrules.api.database import Base
from fluxrules.api.models.audit_policy import AuditPolicy, AuditReport
from fluxrules.api.services.audit_runner import AuditRunner
from fluxrules.api.services.audit_scheduler import compute_next_run


@pytest.fixture()
def db():
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


class TestAuditPolicyCRUD:
    def test_create_policy(self, db):
        policy = AuditPolicy(
            name="Daily Audit",
            cron_expression="0 0 * * *",
            scope="all",
            enabled=True,
        )
        db.add(policy)
        db.commit()
        db.refresh(policy)
        assert policy.id is not None
        assert policy.name == "Daily Audit"

    def test_list_policies(self, db):
        db.add(AuditPolicy(name="P1", cron_expression="0 0 * * *", scope="all"))
        db.add(AuditPolicy(name="P2", cron_expression="0 12 * * *", scope="integrity"))
        db.commit()
        policies = db.query(AuditPolicy).all()
        assert len(policies) >= 2

    def test_delete_policy(self, db):
        policy = AuditPolicy(name="Temp", cron_expression="0 0 * * *", scope="all")
        db.add(policy)
        db.commit()
        pid = policy.id
        db.delete(policy)
        db.commit()
        assert db.query(AuditPolicy).filter(AuditPolicy.id == pid).first() is None

    def test_update_policy(self, db):
        policy = AuditPolicy(name="Update", cron_expression="0 0 * * *", scope="all")
        db.add(policy)
        db.commit()
        policy.scope = "integrity"
        db.commit()
        db.refresh(policy)
        assert policy.scope == "integrity"


class TestAuditRunner:
    def test_run_report(self, db):
        runner = AuditRunner(db)
        report = runner.execute(scope="integrity", triggered_by="manual")
        assert report.id is not None
        assert report.status in ("passed", "warnings", "error")
        assert report.scope == "integrity"

    def test_report_saved_to_db(self, db):
        runner = AuditRunner(db)
        runner.execute(scope="coverage", triggered_by="test")
        reports = db.query(AuditReport).all()
        assert len(reports) >= 1


class TestComputeNextRun:
    def test_valid_cron(self):
        nxt = compute_next_run("0 2 * * *")
        assert nxt is not None
        assert nxt.hour == 2
        assert nxt.minute == 0

    def test_invalid_cron_raises(self):
        with pytest.raises(ValueError):
            compute_next_run("bad cron")
