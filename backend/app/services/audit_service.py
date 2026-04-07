"""Audit-trail service with integrity hashing and retention controls.

Enterprise requirements addressed:

* **Immutability** — audit rows are append-only; no update/delete in app code.
* **Integrity** — each row can be stamped with an HMAC-SHA256 hash keyed by
  ``SECRET_KEY`` so that post-hoc tampering is detectable.
* **Retention** — a configurable ``AUDIT_RETENTION_DAYS`` policy allows old
  entries to be purged by a scheduled maintenance call.
"""

import hashlib
import hmac
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy.orm import Session

from app.config import settings
from app.models.audit import AuditLog

logger = logging.getLogger("fluxrules.audit")


def _compute_integrity_hash(
    action_type: str,
    entity_type: str,
    entity_id: Optional[int],
    user_id: Optional[int],
    details: str,
    timestamp: datetime,
) -> str:
    """Compute an HMAC-SHA256 integrity hash for an audit record.

    The hash covers every business-relevant field so that any post-hoc
    modification of a row can be detected.

    Args:
        action_type: The action performed (e.g. ``"create"``).
        entity_type: The entity kind (e.g. ``"rule"``).
        entity_id: The primary key of the affected entity.
        user_id: The acting user's ID.
        details: Free-text description.
        timestamp: The event timestamp.

    Returns:
        A lowercase hex-encoded HMAC-SHA256 digest (64 characters).
    """
    payload = (
        f"{action_type}|{entity_type}|{entity_id}|"
        f"{user_id}|{details}|{timestamp.isoformat()}"
    )
    return hmac.new(
        settings.SECRET_KEY.encode("utf-8"),
        payload.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def verify_audit_integrity(log: AuditLog) -> bool:
    """Verify that an audit row's integrity hash matches its current content.

    Args:
        log: An ``AuditLog`` ORM instance.

    Returns:
        ``True`` when the stored hash matches a freshly computed one, or when
        the row has no hash (pre-feature rows).  ``False`` if tampered.
    """
    if not log.integrity_hash:
        # Pre-feature row or integrity disabled — cannot verify.
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
    """Append-only audit-trail writer with integrity and retention support."""

    def __init__(self, db: Session):
        self.db = db

    def log_action(
        self,
        action_type: str,
        entity_type: str,
        entity_id: Optional[int],
        user_id: Optional[int],
        details: str,
        execution_time: Optional[float] = None,
        auto_commit: bool = True,
    ) -> AuditLog:
        """Create an immutable audit-log entry.

        When ``AUDIT_INTEGRITY_ENABLED`` is ``True``, the row is stamped
        with an HMAC-SHA256 hash for tamper detection.

        Args:
            action_type: Action label (``"create"``, ``"update"``, …).
            entity_type: Entity kind (``"rule"``, ``"event"``, …).
            entity_id: PK of the affected entity (may be ``None``).
            user_id: Acting user's PK (may be ``None``).
            details: Free-text description.
            execution_time: Optional elapsed time in seconds.
            auto_commit: Commit immediately (default ``True``).

        Returns:
            The persisted ``AuditLog`` instance.
        """
        now = datetime.utcnow()

        integrity_hash: Optional[str] = None
        if settings.AUDIT_INTEGRITY_ENABLED:
            integrity_hash = _compute_integrity_hash(
                action_type, entity_type, entity_id,
                user_id, details, now,
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

    # ------------------------------------------------------------------
    # Retention policy
    # ------------------------------------------------------------------

    def apply_retention_policy(self) -> int:
        """Delete audit rows older than ``AUDIT_RETENTION_DAYS``.

        Returns:
            Number of rows purged.  Returns ``0`` when retention is
            disabled (``AUDIT_RETENTION_DAYS == 0``).
        """
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

    # ------------------------------------------------------------------
    # Integrity verification
    # ------------------------------------------------------------------

    def verify_recent(self, limit: int = 100) -> dict:
        """Spot-check the integrity of recent audit rows.

        Args:
            limit: Maximum number of recent rows to check.

        Returns:
            A dict with ``total_checked``, ``valid``, ``invalid``, and
            ``unprotected`` (rows without a hash) counts.
        """
        rows = (
            self.db.query(AuditLog)
            .order_by(AuditLog.id.desc())
            .limit(limit)
            .all()
        )
        result = {"total_checked": len(rows), "valid": 0, "invalid": 0, "unprotected": 0}
        for row in rows:
            if not row.integrity_hash:
                result["unprotected"] += 1
            elif verify_audit_integrity(row):
                result["valid"] += 1
            else:
                result["invalid"] += 1
        return result
