"""Audit-policy and audit-report persistence models.

These models support **scheduled full-audit runs** with configurable policies.
Each policy defines *what* to audit and *when*, while each report captures the
results of a single audit execution.

.. versionadded:: 1.1.0
   Introduced as part of the production audit-policy feature.

Backward Compatibility
----------------------
* These tables are **additive** — no existing tables or columns are modified.
* The ``audit_policies`` table stores policy configuration (schedule, scope,
  enabled flag).
* The ``audit_reports`` table stores immutable run results with an HMAC
  integrity hash for tamper detection.
"""

from datetime import datetime
from typing import Optional

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
)

from app.database import Base


class AuditPolicy(Base):
    """Configurable policy that governs scheduled full-audit runs.

    Each row represents a named audit policy with a cron-style schedule
    and a scope defining which checks to perform.

    Attributes:
        id: Auto-incrementing primary key.
        name: Human-readable policy name (unique).
        description: Free-text explanation of what this policy audits.
        cron_expression: Cron-syntax schedule (e.g. ``"0 2 * * *"`` for 2 AM
            daily).  Interpreted by the built-in scheduler — no external
            dependency required.
        scope: Comma-separated list of audit check names to run.  Supported
            scopes: ``integrity``, ``retention``, ``coverage``, ``rule_health``,
            ``performance``.  Use ``"all"`` to run every check.
        enabled: Whether the scheduler should honour this policy.
        last_run_at: Timestamp of the most recent execution (``None`` if never
            run).
        next_run_at: Computed next-run timestamp based on
            ``cron_expression``.
        created_by: FK to the admin user who created the policy.
        created_at: Row creation timestamp.
        updated_at: Last modification timestamp.
    """

    __tablename__ = "audit_policies"

    id: int = Column(Integer, primary_key=True, index=True)
    name: str = Column(String, unique=True, nullable=False, index=True)
    description: Optional[str] = Column(Text, nullable=True)
    cron_expression: str = Column(String, nullable=False, default="0 2 * * *")
    scope: str = Column(String, nullable=False, default="all")
    enabled: bool = Column(Boolean, default=True, nullable=False)
    last_run_at: Optional[datetime] = Column(DateTime, nullable=True)
    next_run_at: Optional[datetime] = Column(DateTime, nullable=True)
    created_by: Optional[int] = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at: datetime = Column(DateTime, default=datetime.utcnow)
    updated_at: datetime = Column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )


class AuditReport(Base):
    """Immutable record of a single audit-run execution.

    Every scheduled (or manually triggered) audit produces exactly one
    ``AuditReport`` row.  The ``details_json`` column contains the full
    structured result, while ``integrity_hash`` prevents tampering.

    Attributes:
        id: Auto-incrementing primary key.
        policy_id: FK to the ``AuditPolicy`` that triggered this run
            (``None`` for ad-hoc/manual runs).
        scope: The audit scope that was executed.
        status: Execution outcome: ``"passed"``, ``"warnings"``,
            ``"failed"``, ``"error"``.
        summary: One-line human-readable summary.
        details_json: Full structured result payload (JSON text).
        integrity_violations: Count of integrity-hash mismatches found.
        retention_purged: Number of audit rows purged by retention policy.
        coverage_pct: Rule-coverage percentage at time of audit.
        rules_checked: Total number of rules inspected.
        duration_seconds: Wall-clock time of the audit run.
        integrity_hash: HMAC-SHA256 hash for tamper detection of *this*
            report row.
        triggered_by: ``"schedule"`` or ``"manual"``.
        executed_at: When the audit run started.
    """

    __tablename__ = "audit_reports"

    id: int = Column(Integer, primary_key=True, index=True)
    policy_id: Optional[int] = Column(
        Integer, ForeignKey("audit_policies.id"), nullable=True, index=True
    )
    scope: str = Column(String, nullable=False)
    status: str = Column(String, nullable=False, default="passed")
    summary: Optional[str] = Column(Text, nullable=True)
    details_json: Optional[str] = Column(Text, nullable=True)
    integrity_violations: int = Column(Integer, default=0)
    retention_purged: int = Column(Integer, default=0)
    coverage_pct: float = Column(Float, default=0.0)
    rules_checked: int = Column(Integer, default=0)
    duration_seconds: float = Column(Float, default=0.0)
    integrity_hash: Optional[str] = Column(String(64), nullable=True)
    triggered_by: str = Column(String, nullable=False, default="schedule")
    executed_at: datetime = Column(DateTime, default=datetime.utcnow, index=True)
