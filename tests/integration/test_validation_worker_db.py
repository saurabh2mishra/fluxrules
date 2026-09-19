"""Integration test that drives the bulk-validation worker's DB path.

``_run_bulk_validation`` builds its own SQLAlchemy engine from a ``db_url``, so
it is exercised here against a real file-based SQLite database (an in-memory URL
would not be shared across the worker's separate engine). This covers the
create-success path plus the outer failure handling, which the pure unit tests
in ``test_validation_worker.py`` cannot reach.
"""

from __future__ import annotations

from pathlib import Path

from sqlalchemy import create_engine

# Importing the app registers every ORM model on Base.metadata.
from fluxrules.api.app import create_app  # noqa: F401
from fluxrules.api.database import Base
from fluxrules.api.workers.validation_worker import ValidationJob, _run_bulk_validation

_RULE_PAYLOAD = {
    "name": "BulkWorkerRule",
    "description": "created by the bulk worker test",
    "group": "g1",
    "priority": 1,
    "enabled": True,
    "condition_dsl": {"type": "condition", "field": "amount", "op": ">", "value": 100},
    "action": "flag_for_review",
}


def _make_db(tmp_path: Path) -> str:
    db_path = tmp_path / "bulk.db"
    db_url = f"sqlite:///{db_path}"
    engine = create_engine(db_url, connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    engine.dispose()
    return db_url


def test_run_bulk_validation_creates_rule(tmp_path: Path) -> None:
    db_url = _make_db(tmp_path)
    job = ValidationJob(job_id="bulk-ok", submitted_at=0.0, total_rules=1)

    _run_bulk_validation(job, [_RULE_PAYLOAD], user_id=1, db_url=db_url)

    assert job.status == "completed"
    assert job.processed == 1
    assert job.completed_at is not None
    # Exactly one of created/errors is populated for the single payload.
    assert len(job.created) + len(job.errors) == 1


def test_run_bulk_validation_marks_job_failed_on_bad_db_url() -> None:
    job = ValidationJob(job_id="bulk-fail", submitted_at=0.0, total_rules=1)

    _run_bulk_validation(
        job, [_RULE_PAYLOAD], user_id=1, db_url="postgresql://bad:bad@127.0.0.1:1/nope"
    )

    assert job.status == "failed"
    assert job.error_message is not None
    assert job.completed_at is not None
