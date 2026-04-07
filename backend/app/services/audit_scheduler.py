"""Background audit-policy scheduler using only the standard library.

This module provides a lightweight, production-grade scheduler that runs
in a daemon thread alongside the FastAPI process.  It evaluates cron
expressions using a minimal built-in parser (no ``croniter`` or
``APScheduler`` dependency required).

Architecture
------------
* A single daemon thread sleeps and wakes every 60 seconds.
* On each tick it queries enabled ``AuditPolicy`` rows whose
  ``next_run_at <= now``.
* For each due policy it spawns an ``AuditRunner.execute()`` call inside
  a fresh DB session.
* ``next_run_at`` is recomputed after each run using the cron expression.

The scheduler is started/stopped via :func:`start_audit_scheduler` and
:func:`stop_audit_scheduler`, which are called from the FastAPI
``startup`` / ``shutdown`` events.

Backward Compatibility
----------------------
This module is **opt-in**.  Setting ``AUDIT_SCHEDULER_ENABLED=true`` in
the environment activates it.  The default is ``false`` so existing
deployments are unaffected.

.. versionadded:: 1.1.0
"""

from __future__ import annotations

import logging
import threading
import time
from datetime import datetime, timedelta
from typing import List, Optional

from sqlalchemy.orm import Session

from app.config import settings
from app.database import SessionLocal
from app.models.audit_policy import AuditPolicy

logger = logging.getLogger("fluxrules.audit_scheduler")

# How often the scheduler wakes to check for due policies (seconds).
_TICK_INTERVAL: int = 60

# Module-level scheduler state.
_scheduler_thread: Optional[threading.Thread] = None
_stop_event = threading.Event()


# ---------------------------------------------------------------------------
# Minimal cron expression evaluator (5-field)
# ---------------------------------------------------------------------------


def _parse_cron_field(field: str, min_val: int, max_val: int) -> List[int]:
    """Parse a single cron field into a sorted list of matching integers.

    Supports:
    * ``*`` — every value.
    * ``*/N`` — every *N*-th value.
    * ``N`` — exact value.
    * ``N-M`` — inclusive range.
    * ``N,M,O`` — explicit list.

    Args:
        field: The raw cron field string.
        min_val: Minimum allowed value (inclusive).
        max_val: Maximum allowed value (inclusive).

    Returns:
        Sorted list of integers the field matches.

    Raises:
        ValueError: If the field is malformed.
    """
    values: set[int] = set()
    for part in field.split(","):
        part = part.strip()
        if part == "*":
            values.update(range(min_val, max_val + 1))
        elif part.startswith("*/"):
            step = int(part[2:])
            values.update(range(min_val, max_val + 1, step))
        elif "-" in part:
            lo, hi = part.split("-", 1)
            values.update(range(int(lo), int(hi) + 1))
        else:
            values.add(int(part))
    return sorted(values)


def compute_next_run(cron_expr: str, after: Optional[datetime] = None) -> datetime:
    """Compute the next datetime matching a 5-field cron expression.

    Fields: ``minute hour day-of-month month day-of-week``.

    This is a straightforward brute-force search that advances minute by
    minute from *after* until a match is found.  For production schedules
    (typically hourly or daily) this converges in < 1440 iterations.

    Args:
        cron_expr: 5-field cron string (e.g. ``"0 2 * * *"``).
        after: Start searching from this time.  Defaults to
            ``datetime.utcnow()``.

    Returns:
        The next matching ``datetime`` (always in the future relative to
        *after*).

    Raises:
        ValueError: If the expression does not have exactly 5 fields.
    """
    fields = cron_expr.strip().split()
    if len(fields) != 5:
        raise ValueError(
            f"Cron expression must have 5 fields, got {len(fields)}: {cron_expr!r}"
        )

    minutes = _parse_cron_field(fields[0], 0, 59)
    hours = _parse_cron_field(fields[1], 0, 23)
    days = _parse_cron_field(fields[2], 1, 31)
    months = _parse_cron_field(fields[3], 1, 12)
    weekdays = _parse_cron_field(fields[4], 0, 6)  # 0=Sunday (cron convention)

    if after is None:
        after = datetime.utcnow()
    # Start searching from one minute after *after*.
    candidate = after.replace(second=0, microsecond=0) + timedelta(minutes=1)

    # Safety limit: search at most 366 days ahead.
    limit = after + timedelta(days=366)
    while candidate < limit:
        if (
            candidate.minute in minutes
            and candidate.hour in hours
            and candidate.day in days
            and candidate.month in months
            and candidate.weekday() in _cron_weekday_to_python(weekdays)
        ):
            return candidate
        candidate += timedelta(minutes=1)

    # Fallback: schedule 24h from now if nothing matched.
    return after + timedelta(hours=24)


def _cron_weekday_to_python(cron_days: List[int]) -> set[int]:
    """Convert cron day-of-week (0=Sun) to Python weekday (0=Mon).

    Args:
        cron_days: List of cron day-of-week integers.

    Returns:
        Set of Python weekday integers.
    """
    mapping = {0: 6, 1: 0, 2: 1, 3: 2, 4: 3, 5: 4, 6: 5}
    return {mapping.get(d, d) for d in cron_days}


# ---------------------------------------------------------------------------
# Scheduler loop
# ---------------------------------------------------------------------------


def _scheduler_loop() -> None:
    """Main loop: wake every tick, find due policies, execute audit runs."""
    logger.info("Audit scheduler started (tick=%ds).", _TICK_INTERVAL)
    while not _stop_event.is_set():
        try:
            _process_due_policies()
        except Exception:
            logger.exception("Audit scheduler tick failed — will retry next tick.")
        _stop_event.wait(timeout=_TICK_INTERVAL)
    logger.info("Audit scheduler stopped.")


def _process_due_policies() -> None:
    """Query for due policies and execute them inside a fresh session."""
    db: Session = SessionLocal()
    try:
        now = datetime.utcnow()
        due: List[AuditPolicy] = (
            db.query(AuditPolicy)
            .filter(
                AuditPolicy.enabled.is_(True),
                AuditPolicy.next_run_at <= now,
            )
            .all()
        )
        if not due:
            return

        from app.services.audit_runner import AuditRunner

        for policy in due:
            logger.info(
                "Executing scheduled audit policy '%s' (id=%d, scope=%s).",
                policy.name, policy.id, policy.scope,
            )
            try:
                runner = AuditRunner(db)
                runner.execute(
                    scope=policy.scope,
                    policy_id=policy.id,
                    triggered_by="schedule",
                )
                # Recompute next_run_at.
                policy.next_run_at = compute_next_run(policy.cron_expression, after=now)
                db.commit()
            except Exception:
                db.rollback()
                logger.exception(
                    "Scheduled audit policy '%s' (id=%d) failed.", policy.name, policy.id,
                )
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Public start / stop helpers
# ---------------------------------------------------------------------------


def start_audit_scheduler() -> None:
    """Start the background scheduler daemon thread.

    Safe to call multiple times — subsequent calls are no-ops if the
    scheduler is already running.
    """
    global _scheduler_thread

    if not getattr(settings, "AUDIT_SCHEDULER_ENABLED", False):
        logger.info("Audit scheduler is disabled (AUDIT_SCHEDULER_ENABLED=false).")
        return

    if _scheduler_thread is not None and _scheduler_thread.is_alive():
        logger.debug("Audit scheduler already running.")
        return

    _stop_event.clear()
    _scheduler_thread = threading.Thread(
        target=_scheduler_loop,
        name="audit-scheduler",
        daemon=True,
    )
    _scheduler_thread.start()
    logger.info("Audit scheduler thread started.")


def stop_audit_scheduler() -> None:
    """Signal the scheduler to stop and wait for the thread to exit.

    Safe to call even if the scheduler was never started.
    """
    global _scheduler_thread
    _stop_event.set()
    if _scheduler_thread is not None:
        _scheduler_thread.join(timeout=10)
        _scheduler_thread = None
        logger.info("Audit scheduler thread joined.")
