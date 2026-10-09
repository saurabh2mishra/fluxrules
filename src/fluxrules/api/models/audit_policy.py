"""Audit-policy and audit-report persistence models.

These models support **scheduled full-audit runs** with configurable policies.
Each policy defines *what* to audit and *when*, while each report captures the
results of a single audit execution.

* The ``audit_policies`` table stores policy configuration (schedule, scope,
  enabled flag).
* The ``audit_reports`` table stores immutable run results with an HMAC
  integrity hash for tamper detection.
"""

from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column

from fluxrules.api.database import Base


class AuditPolicy(Base):
    __tablename__ = "audit_policies"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String, unique=True, nullable=False, index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    cron_expression: Mapped[str] = mapped_column(String, nullable=False, default="0 2 * * *")
    scope: Mapped[str] = mapped_column(String, nullable=False, default="all")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    next_run_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_by: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=lambda: datetime.now(timezone.utc).replace(tzinfo=None),
        onupdate=lambda: datetime.now(timezone.utc).replace(tzinfo=None),
    )


class AuditReport(Base):
    __tablename__ = "audit_reports"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    policy_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("audit_policies.id"), nullable=True, index=True
    )
    scope: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False, default="passed")
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    details_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    integrity_violations: Mapped[int] = mapped_column(Integer, default=0)
    retention_purged: Mapped[int] = mapped_column(Integer, default=0)
    coverage_pct: Mapped[float] = mapped_column(Float, default=0.0)
    rules_checked: Mapped[int] = mapped_column(Integer, default=0)
    duration_seconds: Mapped[float] = mapped_column(Float, default=0.0)
    integrity_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    triggered_by: Mapped[str] = mapped_column(String, nullable=False, default="schedule")
    executed_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None), index=True
    )
