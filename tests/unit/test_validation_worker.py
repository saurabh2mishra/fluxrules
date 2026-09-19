"""Unit tests for the background bulk-validation worker.

Exercises the in-memory job registry helpers (``submit_bulk_validation``,
``get_job_status``, ``list_jobs``) and the ``ValidationJob.elapsed_ms``
timing property without touching a real database. The heavy
``_run_bulk_validation`` DB path is driven indirectly by keeping the executor
submission mocked out.
"""

from __future__ import annotations

import pytest

from fluxrules.api.workers import validation_worker as vw
from fluxrules.api.workers.validation_worker import ValidationJob


@pytest.fixture(autouse=True)
def _clean_registry() -> None:
    with vw._jobs_lock:
        vw._jobs.clear()
    yield
    with vw._jobs_lock:
        vw._jobs.clear()


def test_elapsed_ms_uses_completed_when_present() -> None:
    job = ValidationJob(job_id="j", submitted_at=100.0, started_at=100.0, completed_at=100.5)
    assert job.elapsed_ms == pytest.approx(500.0)


def test_elapsed_ms_falls_back_to_submitted_when_not_started() -> None:
    # No started_at/completed_at -> measures from submitted_at to now (>= 0).
    job = ValidationJob(job_id="j", submitted_at=0.0)
    assert job.elapsed_ms > 0


def test_get_job_status_returns_none_for_unknown_id() -> None:
    assert vw.get_job_status("missing") is None


def test_get_job_status_returns_serialisable_snapshot() -> None:
    job = ValidationJob(
        job_id="abc",
        status="completed",
        submitted_at=1.0,
        started_at=1.0,
        completed_at=1.25,
        total_rules=3,
        processed=3,
        created=[{"id": 1, "name": "r1"}],
        errors=[{"index": 2, "error": "boom"}],
    )
    with vw._jobs_lock:
        vw._jobs[job.job_id] = job

    status = vw.get_job_status("abc")
    assert status is not None
    assert status["job_id"] == "abc"
    assert status["created_count"] == 1
    assert status["error_count"] == 1
    assert status["elapsed_ms"] == pytest.approx(250.0)


def test_list_jobs_orders_newest_first_and_respects_limit() -> None:
    for idx, ts in enumerate([10.0, 30.0, 20.0]):
        job = ValidationJob(job_id=f"j{idx}", submitted_at=ts)
        with vw._jobs_lock:
            vw._jobs[job.job_id] = job

    listed = vw.list_jobs(limit=2)
    assert [j["job_id"] for j in listed] == ["j1", "j2"]  # ts 30 then 20


def test_submit_bulk_validation_registers_job(monkeypatch: pytest.MonkeyPatch) -> None:
    submitted: list = []

    class _FakePool:
        def submit(self, fn, *args, **kwargs):
            submitted.append((fn, args))

    monkeypatch.setattr(vw, "_pool", _FakePool())

    job_id = vw.submit_bulk_validation(
        [{"name": "r1"}, {"name": "r2"}], user_id=7, db_url="sqlite://"
    )
    status = vw.get_job_status(job_id)
    assert status is not None
    assert status["total_rules"] == 2
    assert status["status"] == "pending"
    assert len(submitted) == 1
