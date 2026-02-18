from pydantic import BaseModel
from typing import Dict, Any, Optional

class Event(BaseModel):
    event_type: str
    data: Dict[str, Any]
    metadata: Optional[Dict[str, Any]] = None

class EventResponse(BaseModel):
    event_id: str
    status: str
    message: str
