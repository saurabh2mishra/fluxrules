from fastapi import APIRouter, Response, Depends
from prometheus_client import generate_latest, CONTENT_TYPE_LATEST
from sqlalchemy.orm import Session
from app.utils.metrics import get_metrics_registry, get_dashboard_metrics
from app.api.deps import get_db, get_current_user
from app.models.user import User
from app.models.rule import Rule

router = APIRouter(prefix="/metrics", tags=["metrics"])

@router.get("")
def metrics():
    """Raw Prometheus metrics (for Grafana/Prometheus scraping)."""
    registry = get_metrics_registry()
    return Response(content=generate_latest(registry), media_type=CONTENT_TYPE_LATEST)

@router.get("/dashboard")
def dashboard_metrics(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Human-friendly metrics dashboard."""
    # Get rule statistics from database
    total_rules = db.query(Rule).count()
    enabled_rules = db.query(Rule).filter(Rule.enabled == True).count()
    disabled_rules = total_rules - enabled_rules
    
    # Get groups
    groups = db.query(Rule.group).distinct().all()
    group_count = len([g for g in groups if g[0]])
    
    # Get processing metrics
    processing_metrics = get_dashboard_metrics()
    
    return {
        "rules": {
            "total": total_rules,
            "enabled": enabled_rules,
            "disabled": disabled_rules,
            "groups": group_count
        },
        "processing": processing_metrics,
        "engine": {
            "type": "RETE Network",
            "status": "healthy"
        }
    }
