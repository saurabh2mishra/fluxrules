"""Background validation worker for bulk rule operations."""

from __future__ import annotations

import json
import logging
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class ValidationJob:
    job_id: str
    status: str = "pending"
    submitted_at: float = 0.0
    started_at: float | None = None
    completed_at: float | None = None
    total_rules: int = 0
    processed: int = 0
    created: list[dict[str, Any]] = field(default_factory=list)
    errors: list[dict[str, Any]] = field(default_factory=list)
    error_message: str | None = None

    @property
    def elapsed_ms(self) -> float:
        end = self.completed_at or time.time()
        start = self.started_at or self.submitted_at
        return (end - start) * 1000


_jobs: dict[str, ValidationJob] = {}
_jobs_lock = threading.Lock()

_pool = ThreadPoolExecutor(max_workers=4, thread_name_prefix="bulk-validate")


def submit_bulk_validation(
    rule_payloads: list[dict[str, Any]],
    user_id: int,
    db_url: str,
) -> str:
    job_id = str(uuid.uuid4())
    job = ValidationJob(
        job_id=job_id,
        submitted_at=time.time(),
        total_rules=len(rule_payloads),
    )
    with _jobs_lock:
        _jobs[job_id] = job

    _pool.submit(_run_bulk_validation, job, rule_payloads, user_id, db_url)
    return job_id


def get_job_status(job_id: str) -> dict[str, Any] | None:
    with _jobs_lock:
        job = _jobs.get(job_id)
    if job is None:
        return None
    return {
        "job_id": job.job_id,
        "status": job.status,
        "total_rules": job.total_rules,
        "processed": job.processed,
        "created_count": len(job.created),
        "error_count": len(job.errors),
        "elapsed_ms": round(job.elapsed_ms, 1),
        "error_message": job.error_message,
        "created": job.created,
        "errors": job.errors,
    }


def list_jobs(limit: int = 20) -> list[dict[str, Any]]:
    with _jobs_lock:
        jobs = sorted(_jobs.values(), key=lambda j: j.submitted_at, reverse=True)[:limit]
    return [
        {
            "job_id": j.job_id,
            "status": j.status,
            "total_rules": j.total_rules,
            "processed": j.processed,
            "created_count": len(j.created),
            "error_count": len(j.errors),
            "elapsed_ms": round(j.elapsed_ms, 1),
        }
        for j in jobs
    ]


def _run_bulk_validation(
    job: ValidationJob,
    rule_payloads: list[dict[str, Any]],
    user_id: int,
    db_url: str,
) -> None:
    job.status = "running"
    job.started_at = time.time()

    try:
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker

        engine = create_engine(db_url, connect_args={"check_same_thread": False})
        SessionLocal = sessionmaker(bind=engine)
        db = SessionLocal()

        try:
            from fluxrules.api.models.conflicted_rule import ConflictedRule
            from fluxrules.api.schemas.rule import RuleCreate
            from fluxrules.api.services.rule_service import RuleService
            from fluxrules.api.services.rule_validation_service import (
                RuleValidationService,
            )
            from fluxrules.services.validation._compiled_cache import (
                invalidate as invalidate_compiled_cache,
            )

            service = RuleService(db)
            BLOCKING_TYPES = {
                "priority_collision",
                "duplicate_condition",
                "brms_dead_rule",
            }

            for i, payload in enumerate(rule_payloads):
                try:
                    validator = RuleValidationService(db)
                    result = validator.validate(payload)
                    potential_conflicts = result.get("conflicts", [])
                    blocking = [
                        c
                        for c in potential_conflicts
                        if c.get("type") in BLOCKING_TYPES
                        and (
                            c.get("existing_rule_id") is not None
                            or c.get("type") == "brms_dead_rule"
                        )
                    ]

                    if blocking:
                        for conflict in blocking:
                            parked = ConflictedRule(
                                name=payload.get("name"),
                                description=payload.get("description"),
                                group=payload.get("group"),
                                priority=payload.get("priority"),
                                enabled=payload.get("enabled", True),
                                condition_dsl=json.dumps(payload.get("condition_dsl", {})),
                                action=payload.get("action", ""),
                                rule_metadata=json.dumps(payload.get("rule_metadata"))
                                if payload.get("rule_metadata")
                                else None,
                                conflict_type=conflict.get("type", "unknown"),
                                conflict_description=conflict.get("description", ""),
                                conflicting_rule_id=conflict.get("existing_rule_id"),
                                conflicting_rule_name=conflict.get("existing_rule_name"),
                                submitted_by=user_id,
                                status="pending",
                            )
                            db.add(parked)
                        db.commit()
                        job.errors.append(
                            {
                                "index": i,
                                "rule_name": payload.get("name"),
                                "error": "Rule conflicts detected. Rule parked for review.",
                                "parked": True,
                                "conflicts": blocking,
                            }
                        )
                    else:
                        rule_create = RuleCreate(**payload)
                        created = service.create_rule(rule_create, user_id)
                        job.created.append(
                            {
                                "id": created.id,
                                "name": created.name,
                            }
                        )
                except Exception as e:
                    job.errors.append(
                        {
                            "index": i,
                            "rule_name": payload.get("name"),
                            "error": str(e),
                        }
                    )

                job.processed = i + 1

            try:
                invalidate_compiled_cache()
            except Exception:  # noqa: S110 - cache invalidation is best-effort
                pass

        finally:
            db.close()

        job.status = "completed"
    except Exception as e:
        job.status = "failed"
        job.error_message = str(e)
        logger.exception("Bulk validation job %s failed: %s", job.job_id, e)
    finally:
        job.completed_at = time.time()
