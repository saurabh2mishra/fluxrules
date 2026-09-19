from fastapi import APIRouter, Depends, Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from sqlalchemy.orm import Session

from fluxrules.api.database import get_db
from fluxrules.api.deps import get_current_user
from fluxrules.api.models.rule import Rule
from fluxrules.api.models.user import User
from fluxrules.api.services.analytics_service import get_analytics_service
from fluxrules.api.utils.metrics import get_metrics_registry

router = APIRouter(prefix="/metrics", tags=["metrics"])


@router.get("")
def metrics():
    registry = get_metrics_registry()
    return Response(content=generate_latest(registry), media_type=CONTENT_TYPE_LATEST)


@router.get("/dashboard")
def dashboard_metrics(
    db: Session = Depends(get_db), current_user: User = Depends(get_current_user)
):
    total_rules = db.query(Rule).count()
    enabled_rules = db.query(Rule).filter(Rule.enabled).count()
    disabled_rules = total_rules - enabled_rules

    groups = db.query(Rule.group).distinct().all()
    group_count = len([g for g in groups if g[0]])

    summary = get_analytics_service().get_runtime_summary(db)
    processing_metrics = {
        "events_processed": summary.events_processed,
        "rules_fired": summary.rules_fired,
        "avg_processing_time_ms": summary.avg_processing_time_ms,
        "total_evaluations": summary.events_processed,
    }

    return {
        "rules": {
            "total": total_rules,
            "enabled": enabled_rules,
            "disabled": disabled_rules,
            "groups": group_count,
        },
        "processing": processing_metrics,
        "engine": {"type": "PHREAK", "status": "healthy"},
    }
