"""Background audit-policy scheduler."""

from __future__ import annotations

import logging
import threading
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from fluxrules.api.config import settings
from fluxrules.api.database import SessionLocal
from fluxrules.api.models.audit_policy import AuditPolicy

logger = logging.getLogger("fluxrules.audit_scheduler")

_TICK_INTERVAL: int = 60

_scheduler_thread: threading.Thread | None = None
_stop_event = threading.Event()


def _parse_cron_field(field: str, min_val: int, max_val: int) -> list[int]:
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


def compute_next_run(cron_expr: str, after: datetime | None = None) -> datetime:
    fields = cron_expr.strip().split()
    if len(fields) != 5:
        raise ValueError(f"Cron expression must have 5 fields, got {len(fields)}: {cron_expr!r}")

    minutes = _parse_cron_field(fields[0], 0, 59)
    hours = _parse_cron_field(fields[1], 0, 23)
    days = _parse_cron_field(fields[2], 1, 31)
    months = _parse_cron_field(fields[3], 1, 12)
    weekdays = _parse_cron_field(fields[4], 0, 6)

    if after is None:
        after = datetime.utcnow()
    candidate = after.replace(second=0, microsecond=0) + timedelta(minutes=1)

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

    return after + timedelta(hours=24)


def _cron_weekday_to_python(cron_days: list[int]) -> set[int]:
    mapping = {0: 6, 1: 0, 2: 1, 3: 2, 4: 3, 5: 4, 6: 5}
    return {mapping.get(d, d) for d in cron_days}


def _scheduler_loop() -> None:
    logger.info("Audit scheduler started (tick=%ds).", _TICK_INTERVAL)
    while not _stop_event.is_set():
        try:
            _process_due_policies()
        except Exception:
            logger.exception("Audit scheduler tick failed - will retry next tick.")
        _stop_event.wait(timeout=_TICK_INTERVAL)
    logger.info("Audit scheduler stopped.")


def _process_due_policies() -> None:
    db: Session = SessionLocal()
    try:
        now = datetime.utcnow()
        due: list[AuditPolicy] = (
            db.query(AuditPolicy)
            .filter(
                AuditPolicy.enabled.is_(True),
                AuditPolicy.next_run_at <= now,
            )
            .all()
        )
        if not due:
            return

        from fluxrules.api.services.audit_runner import AuditRunner

        for policy in due:
            logger.info(
                "Executing scheduled audit policy '%s' (id=%d, scope=%s).",
                policy.name,
                policy.id,
                policy.scope,
            )
            try:
                runner = AuditRunner(db)
                runner.execute(
                    scope=policy.scope,
                    policy_id=policy.id,
                    triggered_by="schedule",
                )
                policy.next_run_at = compute_next_run(policy.cron_expression, after=now)
                db.commit()
            except Exception:
                db.rollback()
                logger.exception(
                    "Scheduled audit policy '%s' (id=%d) failed.",
                    policy.name,
                    policy.id,
                )
    finally:
        db.close()


def start_audit_scheduler() -> None:
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
    global _scheduler_thread
    _stop_event.set()
    if _scheduler_thread is not None:
        _scheduler_thread.join(timeout=10)
        _scheduler_thread = None
        logger.info("Audit scheduler thread joined.")
