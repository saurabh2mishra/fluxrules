"""Admin API routes for audit-policy management and reporting."""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from fluxrules.api.deps import get_current_admin, get_db
from fluxrules.api.models.audit_policy import AuditPolicy, AuditReport
from fluxrules.api.models.user import User
from fluxrules.api.schemas.audit_policy import (
    AuditPolicyCreate,
    AuditPolicyResponse,
    AuditPolicyUpdate,
    AuditReportDetail,
    AuditReportSummary,
    AuditRunRequest,
    AuditRunResponse,
)
from fluxrules.api.services.audit_runner import AuditRunner
from fluxrules.api.services.audit_scheduler import compute_next_run

router = APIRouter(prefix="/admin", tags=["admin", "audit-policy"])


@router.post("/audit-policy", response_model=AuditPolicyResponse)
def create_audit_policy(
    body: AuditPolicyCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin),
) -> AuditPolicy:
    existing = db.query(AuditPolicy).filter(AuditPolicy.name == body.name).first()
    if existing:
        raise HTTPException(status_code=409, detail=f"Policy '{body.name}' already exists.")

    next_run = compute_next_run(body.cron_expression)
    policy = AuditPolicy(
        name=body.name,
        description=body.description,
        cron_expression=body.cron_expression,
        scope=body.scope,
        enabled=body.enabled,
        next_run_at=next_run,
        created_by=current_user.id,
    )
    db.add(policy)
    db.commit()
    db.refresh(policy)
    return policy


@router.get("/audit-policy", response_model=list[AuditPolicyResponse])
def list_audit_policies(
    enabled_only: bool = Query(False),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin),
) -> list:
    query = db.query(AuditPolicy)
    if enabled_only:
        query = query.filter(AuditPolicy.enabled.is_(True))
    return query.order_by(AuditPolicy.id).all()


@router.get("/audit-policy/{policy_id}", response_model=AuditPolicyResponse)
def get_audit_policy(
    policy_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin),
) -> AuditPolicy:
    policy = db.query(AuditPolicy).filter(AuditPolicy.id == policy_id).first()
    if not policy:
        raise HTTPException(status_code=404, detail="Audit policy not found.")
    return policy


@router.patch("/audit-policy/{policy_id}", response_model=AuditPolicyResponse)
def update_audit_policy(
    policy_id: int,
    body: AuditPolicyUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin),
) -> AuditPolicy:
    policy = db.query(AuditPolicy).filter(AuditPolicy.id == policy_id).first()
    if not policy:
        raise HTTPException(status_code=404, detail="Audit policy not found.")

    update_data = body.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(policy, field, value)

    if "cron_expression" in update_data:
        policy.next_run_at = compute_next_run(policy.cron_expression)

    db.commit()
    db.refresh(policy)
    return policy


@router.delete("/audit-policy/{policy_id}")
def delete_audit_policy(
    policy_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin),
) -> dict:
    policy = db.query(AuditPolicy).filter(AuditPolicy.id == policy_id).first()
    if not policy:
        raise HTTPException(status_code=404, detail="Audit policy not found.")
    db.delete(policy)
    db.commit()
    return {"detail": f"Policy '{policy.name}' deleted."}


@router.post("/audit-run", response_model=AuditRunResponse)
def trigger_audit_run(
    body: AuditRunRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin),
) -> dict:
    runner = AuditRunner(db)
    report = runner.execute(
        scope=body.scope,
        policy_id=body.policy_id,
        triggered_by="manual",
    )
    return {
        "report_id": report.id,
        "status": report.status,
        "summary": report.summary or "",
        "details": json.loads(report.details_json) if report.details_json else {},
    }


@router.get("/audit-report", response_model=list[AuditReportSummary])
def list_audit_reports(
    policy_id: int | None = Query(None),
    status: str | None = Query(None),
    limit: int = Query(50, ge=1, le=500),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin),
) -> list:
    query = db.query(AuditReport)
    if policy_id is not None:
        query = query.filter(AuditReport.policy_id == policy_id)
    if status is not None:
        query = query.filter(AuditReport.status == status)
    return query.order_by(AuditReport.executed_at.desc()).limit(limit).all()


@router.get("/audit-report/{report_id}", response_model=AuditReportDetail)
def get_audit_report(
    report_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin),
) -> AuditReport:
    report = db.query(AuditReport).filter(AuditReport.id == report_id).first()
    if not report:
        raise HTTPException(status_code=404, detail="Audit report not found.")
    return report
