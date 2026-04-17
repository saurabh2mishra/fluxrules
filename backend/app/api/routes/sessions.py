from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.execution.session_manager import SessionManager, get_session_manager

router = APIRouter(prefix="/sessions", tags=["sessions"])


class SessionCreateRequest(BaseModel):
    session_id: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class SessionResponse(BaseModel):
    session_id: str
    facts: Dict[str, Dict[str, Any]]
    metadata: Dict[str, Any]
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class FactAssertionRequest(BaseModel):
    fact_id: str
    payload: Dict[str, Any]


@router.post("", response_model=SessionResponse)
def create_session(
    req: SessionCreateRequest,
    manager: SessionManager = Depends(get_session_manager),
):
    ctx = manager.create_session(session_id=req.session_id, metadata=req.metadata)
    return SessionResponse(**ctx.to_dict())


@router.get("", response_model=List[SessionResponse])
def list_sessions(manager: SessionManager = Depends(get_session_manager)):
    return [SessionResponse(**ctx.to_dict()) for ctx in manager.list_sessions()]


@router.get("/{session_id}", response_model=SessionResponse)
def get_session(session_id: str, manager: SessionManager = Depends(get_session_manager)):
    ctx = manager.get_session(session_id)
    if ctx is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return SessionResponse(**ctx.to_dict())


@router.delete("/{session_id}")
def delete_session(session_id: str, manager: SessionManager = Depends(get_session_manager)):
    if not manager.delete_session(session_id):
        raise HTTPException(status_code=404, detail="Session not found")
    return {"status": "deleted", "session_id": session_id}


@router.post("/{session_id}/facts")
def assert_fact(
    session_id: str,
    req: FactAssertionRequest,
    manager: SessionManager = Depends(get_session_manager),
):
    fact = manager.assert_fact(session_id=session_id, fact_id=req.fact_id, payload=req.payload)
    return {"session_id": session_id, "fact_id": req.fact_id, "fact": fact}


@router.delete("/{session_id}/facts/{fact_id}")
def retract_fact(
    session_id: str,
    fact_id: str,
    manager: SessionManager = Depends(get_session_manager),
):
    if not manager.retract_fact(session_id=session_id, fact_id=fact_id):
        raise HTTPException(status_code=404, detail="Fact not found")
    return {"status": "retracted", "session_id": session_id, "fact_id": fact_id}
