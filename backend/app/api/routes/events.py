from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.database import get_db
from app.schemas.event import Event, EventResponse
from app.api.deps import get_current_user
from app.models.user import User
from app.utils.redis_client import get_redis_client
import uuid
import json

router = APIRouter(prefix="/events", tags=["events"])

@router.post("", response_model=EventResponse)
def submit_event(
    event: Event,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    redis_client = get_redis_client()
    event_id = str(uuid.uuid4())
    
    event_data = {
        "event_id": event_id,
        "event_type": event.event_type,
        "data": event.data,
        "metadata": event.metadata or {},
        "user_id": current_user.id
    }
    
    redis_client.lpush("event_queue", json.dumps(event_data))
    
    return EventResponse(
        event_id=event_id,
        status="queued",
        message="Event submitted for processing"
    )
