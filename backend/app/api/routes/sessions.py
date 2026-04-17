from __future__ import annotations

from datetime import datetime, timezone
from threading import Lock
from typing import Any, Dict
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.deps import get_current_user
from app.models.user import User
from app.schemas.session import (
    AssertFactRequest,
    AssertFactResponse,
    SessionCreate,
    SessionResponse,
    SessionStatsResponse,
)

router = APIRouter(prefix="/sessions", tags=["sessions"])

MAX_FACTS_PER_SESSION = 100

_STORE_LOCK = Lock()
_SESSIONS: dict[str, dict[str, Any]] = {}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _session_not_found(session_id: str) -> HTTPException:
    return HTTPException(status_code=404, detail=f"Session '{session_id}' not found")


def _get_owned_session(session_id: str, user_id: int) -> dict[str, Any]:
    session = _SESSIONS.get(session_id)
    if session is None:
        raise _session_not_found(session_id)
    if session["user_id"] != user_id:
        raise _session_not_found(session_id)
    return session


def reset_session_store() -> None:
    """Test helper: clear in-memory session state."""
    with _STORE_LOCK:
        _SESSIONS.clear()


@router.post("", response_model=SessionResponse, status_code=status.HTTP_201_CREATED)
def create_session(
    payload: SessionCreate,
    current_user: User = Depends(get_current_user),
) -> SessionResponse:
    now = _utcnow()
    session_id = str(uuid4())

    with _STORE_LOCK:
        _SESSIONS[session_id] = {
            "id": session_id,
            "user_id": current_user.id,
            "metadata": dict(payload.metadata),
            "facts": {},
            "created_at": now,
            "updated_at": now,
        }

    return SessionResponse(
        id=session_id,
        user_id=current_user.id,
        metadata=dict(payload.metadata),
        fact_count=0,
        created_at=now,
        updated_at=now,
    )


@router.post("/{id}/facts", response_model=AssertFactResponse, status_code=status.HTTP_201_CREATED)
def assert_fact(
    id: str,
    payload: AssertFactRequest,
    current_user: User = Depends(get_current_user),
) -> AssertFactResponse:
    now = _utcnow()
    fact_id = str(uuid4())

    with _STORE_LOCK:
        session = _get_owned_session(id, current_user.id)
        if len(session["facts"]) >= MAX_FACTS_PER_SESSION:
            raise HTTPException(status_code=429, detail="Session fact limit reached")

        fact_record = {
            "fact_id": fact_id,
            "session_id": id,
            "fact": dict(payload.fact),
            "created_at": now,
        }
        session["facts"][fact_id] = fact_record
        session["updated_at"] = now

    return AssertFactResponse(**fact_record)


@router.get("/{id}", response_model=SessionStatsResponse)
def get_session(
    id: str,
    current_user: User = Depends(get_current_user),
) -> SessionStatsResponse:
    with _STORE_LOCK:
        session = _get_owned_session(id, current_user.id)
        return SessionStatsResponse(
            session_id=id,
            total_facts=len(session["facts"]),
            created_at=session["created_at"],
            updated_at=session["updated_at"],
        )


@router.get("/{id}/facts", response_model=list[AssertFactResponse])
def list_facts(
    id: str,
    current_user: User = Depends(get_current_user),
) -> list[AssertFactResponse]:
    with _STORE_LOCK:
        session = _get_owned_session(id, current_user.id)
        return [AssertFactResponse(**fact) for fact in session["facts"].values()]


@router.delete("/{id}/facts/{fact_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_fact(
    id: str,
    fact_id: str,
    current_user: User = Depends(get_current_user),
) -> None:
    with _STORE_LOCK:
        session = _get_owned_session(id, current_user.id)
        if fact_id not in session["facts"]:
            raise HTTPException(
                status_code=404,
                detail=f"Fact '{fact_id}' not found in session '{id}'",
            )
        del session["facts"][fact_id]
        session["updated_at"] = _utcnow()


@router.delete("/{id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_session(
    id: str,
    current_user: User = Depends(get_current_user),
) -> None:
    with _STORE_LOCK:
        _get_owned_session(id, current_user.id)
        del _SESSIONS[id]
