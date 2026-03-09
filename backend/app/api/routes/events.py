import json
import uuid
from time import perf_counter

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.database import get_db
from app.engine.rete_engine import ReteEngine
from app.models.user import User
from app.schemas.event import Event, EventResponse
from app.services.analytics_service import get_analytics_service
from app.services.audit_service import AuditService
from app.utils.redis_client import get_redis_client
from app.utils.metrics import increment_events_processed, increment_rules_fired, observe_processing_time

router = APIRouter(prefix="/events", tags=["events"])


@router.post("", response_model=EventResponse)
def submit_event(
    event: Event,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    redis_client = get_redis_client()
    event_id = str(uuid.uuid4())

    event_data = {
        "event_id": event_id,
        "event_type": event.event_type,
        "data": event.data,
        "metadata": event.metadata or {},
        "user_id": current_user.id,
    }

    if redis_client:
        redis_client.lpush("event_queue", json.dumps(event_data))
        return EventResponse(
            event_id=event_id,
            status="queued",
            message="Event submitted for processing",
        )

    # Redis is optional: process synchronously for lightweight local setups
    start = perf_counter()
    engine = ReteEngine(db)
    result = engine.simulate(event.data)
    matched_rules = result.get("matched_rules", [])
    explanations = result.get("explanations", {})

    audit_service = AuditService(db)
    analytics_service = get_analytics_service()

    per_rule_ms = ((perf_counter() - start) * 1000 / max(len(matched_rules), 1))
    for matched_rule in matched_rules:
        audit_service.log_action(
            "rule_fired",
            "rule",
            matched_rule["id"],
            current_user.id,
            f"Rule fired for event {event_id}",
        )
        increment_rules_fired()
        analytics_service.record_rule_execution(
            str(matched_rule["id"]),
            per_rule_ms,
            event.data,
            explanation=explanations.get(matched_rule["id"]) or explanations.get(str(matched_rule["id"])),
        )

    elapsed_s = perf_counter() - start
    observe_processing_time(elapsed_s)
    increment_events_processed()
    analytics_service.record_event_processed(elapsed_s * 1000)

    audit_service.log_action(
        "event_processed",
        "event",
        None,
        current_user.id,
        f"Event {event_id} processed (sync fallback)",
        elapsed_s,
    )

    return EventResponse(
        event_id=event_id,
        status="processed",
        message="Event processed synchronously because Redis is unavailable",
    )
