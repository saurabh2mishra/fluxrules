"""Audit-trail service with integrity hashing and retention controls."""

import hashlib
import hmac
import logging
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from fluxrules.api.config import get_secret_key, settings
from fluxrules.api.models.audit import AuditLog

logger = logging.getLogger("fluxrules.audit")


def _compute_integrity_hash(
    action_type: str,
    entity_type: str,
    entity_id: int | None,
    user_id: int | None,
    details: str,
    timestamp: datetime,
) -> str:
    payload = f"{action_type}|{entity_type}|{entity_id}|{user_id}|{details}|{timestamp.isoformat()}"
    return hmac.new(
        get_secret_key().encode("utf-8"),
        payload.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def verify_audit_integrity(log: AuditLog) -> bool:
    if not log.integrity_hash:
        return True
    expected = _compute_integrity_hash(
        log.action_type,
        log.entity_type,
        log.entity_id,
        log.user_id,
        log.details or "",
        log.timestamp,
    )
    return hmac.compare_digest(log.integrity_hash, expected)


class AuditService:
    def __init__(self, db: Session):
        self.db = db

    def log_action(
        self,
        action_type: str,
        entity_type: str,
        entity_id: int | None,
        user_id: int | None,
        details: str,
        execution_time: float | None = None,
        auto_commit: bool = True,
    ) -> AuditLog:
        now = datetime.utcnow()

        integrity_hash: str | None = None
        if settings.AUDIT_INTEGRITY_ENABLED:
            integrity_hash = _compute_integrity_hash(
                action_type,
                entity_type,
                entity_id,
                user_id,
                details,
                now,
            )

        log = AuditLog(
            action_type=action_type,
            entity_type=entity_type,
            entity_id=entity_id,
            user_id=user_id,
            details=details,
            execution_time=execution_time,
            timestamp=now,
            integrity_hash=integrity_hash,
        )
        self.db.add(log)
        if auto_commit:
            self.db.commit()
        return log

    def apply_retention_policy(self) -> int:
        days = settings.AUDIT_RETENTION_DAYS
        if days <= 0:
            return 0

        cutoff = datetime.utcnow() - timedelta(days=days)
        count = (
            self.db.query(AuditLog)
            .filter(AuditLog.timestamp < cutoff)
            .delete(synchronize_session=False)
        )
        self.db.commit()
        logger.info("Audit retention: purged %d rows older than %d days.", count, days)
        return count

    def verify_recent(self, limit: int = 100) -> dict:
        rows = self.db.query(AuditLog).order_by(AuditLog.id.desc()).limit(limit).all()
        result = {
            "total_checked": len(rows),
            "valid": 0,
            "invalid": 0,
            "unprotected": 0,
        }
        for row in rows:
            if not row.integrity_hash:
                result["unprotected"] += 1
            elif verify_audit_integrity(row):
                result["valid"] += 1
            else:
                result["invalid"] += 1
        return result
