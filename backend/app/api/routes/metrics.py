from fastapi import APIRouter, Response
from prometheus_client import generate_latest, CONTENT_TYPE_LATEST
from app.utils.metrics import get_metrics_registry

router = APIRouter(prefix="/metrics", tags=["metrics"])

@router.get("")
def metrics():
    registry = get_metrics_registry()
    return Response(content=generate_latest(registry), media_type=CONTENT_TYPE_LATEST)
