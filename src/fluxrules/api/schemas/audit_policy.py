from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class AuditPolicyBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    description: str | None = None
    cron_expression: str = Field(
        default="0 2 * * *",
        description="Cron expression for scheduling (5-field).",
    )
    scope: str = Field(
        default="all",
        description='Comma-separated audit scopes or "all".',
    )
    enabled: bool = True


class AuditPolicyCreate(AuditPolicyBase):
    pass


class AuditPolicyUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=200)
    description: str | None = None
    cron_expression: str | None = None
    scope: str | None = None
    enabled: bool | None = None


class AuditPolicyResponse(AuditPolicyBase):
    id: int
    last_run_at: datetime | None = None
    next_run_at: datetime | None = None
    created_by: int | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    model_config = {"from_attributes": True}


class AuditReportSummary(BaseModel):
    id: int
    policy_id: int | None = None
    scope: str
    status: str
    summary: str | None = None
    integrity_violations: int = 0
    retention_purged: int = 0
    coverage_pct: float = 0.0
    rules_checked: int = 0
    duration_seconds: float = 0.0
    triggered_by: str = "schedule"
    executed_at: datetime | None = None

    model_config = {"from_attributes": True}


class AuditReportDetail(AuditReportSummary):
    details_json: str | None = None
    integrity_hash: str | None = None

    model_config = {"from_attributes": True}


class AuditRunRequest(BaseModel):
    scope: str = Field(default="all", description="Comma-separated scopes or 'all'.")
    policy_id: int | None = None


class AuditRunResponse(BaseModel):
    report_id: int
    status: str
    summary: str
    details: dict[str, Any] = Field(default_factory=dict)
