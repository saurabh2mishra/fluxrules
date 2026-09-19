from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class SessionCreate(BaseModel):
    session_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class SessionResponse(BaseModel):
    id: str
    user_id: int
    metadata: dict[str, Any] = Field(default_factory=dict)
    fact_count: int = 0
    created_at: datetime
    updated_at: datetime


class AssertFactRequest(BaseModel):
    fact: dict[str, Any] = Field(default_factory=dict)
    fact_id: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)


class AssertFactResponse(BaseModel):
    fact_id: str
    session_id: str
    fact: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime


class SessionStatsResponse(BaseModel):
    session_id: str
    total_facts: int
    created_at: datetime
    updated_at: datetime
