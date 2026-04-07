"""Pydantic schemas for the audit-policy and audit-report API surface.

All schemas use ``model_config`` with ``from_attributes = True`` so that
ORM instances can be serialised directly.

.. versionadded:: 1.1.0
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Audit Policy schemas
# ---------------------------------------------------------------------------


class AuditPolicyBase(BaseModel):
    """Shared fields for creating and reading audit policies.

    Attributes:
        name: Human-readable unique policy name.
        description: Optional explanation of this policy's purpose.
        cron_expression: Cron schedule string (e.g. ``"0 2 * * *"``).
        scope: Comma-separated check names or ``"all"``.
        enabled: Whether the policy is active.
    """

    name: str = Field(..., min_length=1, max_length=200)
    description: Optional[str] = None
    cron_expression: str = Field(
        default="0 2 * * *",
        description=(
            'Cron expression for scheduling (5-field). '
            'E.g. "0 2 * * *" = every day at 02:00 UTC.'
        ),
    )
    scope: str = Field(
        default="all",
        description=(
            'Comma-separated audit scopes: integrity, retention, '
            'coverage, rule_health, performance, or "all".'
        ),
    )
    enabled: bool = True


class AuditPolicyCreate(AuditPolicyBase):
    """Request body for creating a new audit policy."""

    pass


class AuditPolicyUpdate(BaseModel):
    """Request body for partially updating an existing audit policy.

    All fields are optional; only supplied fields are applied.
    """

    name: Optional[str] = Field(None, min_length=1, max_length=200)
    description: Optional[str] = None
    cron_expression: Optional[str] = None
    scope: Optional[str] = None
    enabled: Optional[bool] = None


class AuditPolicyResponse(AuditPolicyBase):
    """Read-only representation of a persisted audit policy."""

    id: int
    last_run_at: Optional[datetime] = None
    next_run_at: Optional[datetime] = None
    created_by: Optional[int] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Audit Report schemas
# ---------------------------------------------------------------------------


class AuditReportSummary(BaseModel):
    """Lightweight summary suitable for list views.

    Attributes:
        id: Report primary key.
        policy_id: Associated policy (``None`` for ad-hoc runs).
        scope: The audit scope that was executed.
        status: Outcome: ``"passed"``, ``"warnings"``, ``"failed"``, ``"error"``.
        summary: One-line human-readable summary.
        integrity_violations: Count of hash mismatches found.
        retention_purged: Rows purged by retention.
        coverage_pct: Rule-coverage percentage.
        rules_checked: Total rules inspected.
        duration_seconds: Wall-clock run time.
        triggered_by: ``"schedule"`` or ``"manual"``.
        executed_at: Run timestamp.
    """

    id: int
    policy_id: Optional[int] = None
    scope: str
    status: str
    summary: Optional[str] = None
    integrity_violations: int = 0
    retention_purged: int = 0
    coverage_pct: float = 0.0
    rules_checked: int = 0
    duration_seconds: float = 0.0
    triggered_by: str = "schedule"
    executed_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class AuditReportDetail(AuditReportSummary):
    """Full report including the raw JSON details payload."""

    details_json: Optional[str] = None
    integrity_hash: Optional[str] = None

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Manual trigger request / response
# ---------------------------------------------------------------------------


class AuditRunRequest(BaseModel):
    """Request body for triggering a manual audit run.

    Attributes:
        scope: Override the default scope for this run.
        policy_id: Optionally link to an existing policy.
    """

    scope: str = Field(
        default="all",
        description="Comma-separated scopes or 'all'.",
    )
    policy_id: Optional[int] = None


class AuditRunResponse(BaseModel):
    """Response returned immediately after triggering an audit run.

    Attributes:
        report_id: The ``AuditReport.id`` created for this run.
        status: Overall outcome.
        summary: Human-readable one-liner.
        details: Structured result dict.
    """

    report_id: int
    status: str
    summary: str
    details: Dict[str, Any] = Field(default_factory=dict)
