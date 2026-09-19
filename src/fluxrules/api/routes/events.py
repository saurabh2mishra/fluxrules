import json
import uuid
from time import perf_counter

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from fluxrules.api.config import settings
from fluxrules.api.database import get_db
from fluxrules.api.deps import get_current_user
from fluxrules.api.engines import APIEngineAdapter
from fluxrules.api.models.user import User
from fluxrules.api.schemas.event import Event, EventResponse
from fluxrules.api.services.analytics_service import get_analytics_service
from fluxrules.api.services.audit_service import AuditService
from fluxrules.api.utils.metrics import (
    increment_events_processed,
    increment_rules_fired,
    observe_processing_time,
)
from fluxrules.api.utils.redis_client import get_redis_client

router = APIRouter(prefix="/event", tags=["events"])


@router.post("", response_model=EventResponse)
def process_event(
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

    start = perf_counter()
    adapter = APIEngineAdapter(engine_type=settings.RULE_ENGINE_TYPE, db=db, enable_cache=True)
    result = adapter.evaluate(event.data)
    matched_rules = result.get("matched_rules", [])
    explanations = result.get("explanations", {})

    audit_service = AuditService(db)
    analytics_service = get_analytics_service()

    per_rule_ms = (perf_counter() - start) * 1000 / max(len(matched_rules), 1)
    for matched_rule in matched_rules:
        # matched_rule can be a dict or just a rule ID
        rule_id = matched_rule.get("id") if isinstance(matched_rule, dict) else matched_rule
        audit_service.log_action(
            "rule_fired",
            "rule",
            rule_id,
            current_user.id,
            f"Rule fired for event {event_id}",
        )
        increment_rules_fired()
        analytics_service.record_rule_execution(
            str(rule_id),
            per_rule_ms,
            event.data,
            explanation=explanations.get(rule_id) or explanations.get(str(rule_id)),
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
