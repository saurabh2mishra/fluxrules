from typing import Any

from pydantic import BaseModel


class Event(BaseModel):
    event_type: str
    data: dict[str, Any]
    metadata: dict[str, Any] | None = None


class EventResponse(BaseModel):
    event_id: str
    status: str
    message: str
