from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.models.user import User
from app.services.analytics_service import get_analytics_service

router = APIRouter(prefix="/analytics", tags=["analytics"])


@router.get("/runtime")
def runtime_analytics(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return get_analytics_service().get_runtime_analytics(db).model_dump()


@router.get("/rules/top")
def top_rules(
    limit: int = Query(10, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return get_analytics_service().get_top_rules(db, limit=limit).model_dump()


@router.get("/rules/{rule_id}")
def rule_metrics(
    rule_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return get_analytics_service().get_rule_metrics(db, rule_id=rule_id).model_dump()


@router.get("/explanations")
def explanations(
    rule_id: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    data = get_analytics_service().get_recent_explanations(rule_id=rule_id, limit=limit)
    return {"items": [x.model_dump() for x in data]}


@router.get("/coverage")
def coverage(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return get_analytics_service().get_coverage(db).model_dump()
