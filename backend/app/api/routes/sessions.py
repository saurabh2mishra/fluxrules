from __future__ import annotations

from datetime import datetime, timezone
from threading import Lock
from typing import Any, Dict
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Response, status

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


@router.post("", response_model=SessionResponse)
def create_session(
    payload: SessionCreate,
    response: Response,
    current_user: User = Depends(get_current_user),
) -> SessionResponse:
    now = _utcnow()
    session_id = payload.session_id or str(uuid4())
    compat_mode = payload.session_id is not None

    with _STORE_LOCK:
        _SESSIONS[session_id] = {
            "id": session_id,
            "user_id": current_user.id,
            "metadata": dict(payload.metadata),
            "facts": {},
            "compat_mode": compat_mode,
            "created_at": now,
            "updated_at": now,
        }

    session_response = SessionResponse(
        id=session_id,
        user_id=current_user.id,
        metadata=dict(payload.metadata),
        fact_count=0,
        created_at=now,
        updated_at=now,
    )
    response.status_code = status.HTTP_200_OK if compat_mode else status.HTTP_201_CREATED
    return session_response


@router.post("/{id}/facts", response_model=AssertFactResponse)
def assert_fact(
    id: str,
    payload: AssertFactRequest,
    response: Response,
    current_user: User = Depends(get_current_user),
) -> AssertFactResponse:
    now = _utcnow()
    fact_id = payload.fact_id or str(uuid4())

    with _STORE_LOCK:
        session = _get_owned_session(id, current_user.id)
        if len(session["facts"]) >= MAX_FACTS_PER_SESSION:
            raise HTTPException(status_code=429, detail="Session fact limit reached")

        fact_payload = dict(payload.payload or payload.fact)
        fact_record = {
            "fact_id": fact_id,
            "session_id": id,
            "fact": fact_payload,
            "created_at": now,
        }
        session["facts"][fact_id] = fact_record
        session["updated_at"] = now

    response.status_code = status.HTTP_200_OK if payload.fact_id is not None else status.HTTP_201_CREATED
    return AssertFactResponse(**fact_record)


@router.get("/{id}")
def get_session(
    id: str,
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    with _STORE_LOCK:
        session = _get_owned_session(id, current_user.id)
        response = SessionStatsResponse(
            session_id=id,
            total_facts=len(session["facts"]),
            created_at=session["created_at"],
            updated_at=session["updated_at"],
        ).model_dump()
        response["facts"] = {fid: rec["fact"] for fid, rec in session["facts"].items()}
        response["metadata"] = dict(session["metadata"])
        return response


@router.get("")
def list_sessions(
    current_user: User = Depends(get_current_user),
) -> list[dict[str, Any]]:
    with _STORE_LOCK:
        return [
            {
                "session_id": sid,
                "facts": {fid: rec["fact"] for fid, rec in sess["facts"].items()},
                "metadata": dict(sess["metadata"]),
            }
            for sid, sess in _SESSIONS.items()
            if sess["user_id"] == current_user.id
        ]


@router.get("/{id}/facts", response_model=list[AssertFactResponse])
def list_facts(
    id: str,
    current_user: User = Depends(get_current_user),
) -> list[AssertFactResponse]:
    with _STORE_LOCK:
        session = _get_owned_session(id, current_user.id)
        return [AssertFactResponse(**fact) for fact in session["facts"].values()]


@router.delete("/{id}/facts/{fact_id}")
def delete_fact(
    id: str,
    fact_id: str,
    response: Response,
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
        if session.get("compat_mode"):
            response.status_code = status.HTTP_200_OK
            return {"deleted": True}
        response.status_code = status.HTTP_204_NO_CONTENT
        return None


@router.delete("/{id}")
def delete_session(
    id: str,
    response: Response,
    current_user: User = Depends(get_current_user),
) -> None:
    with _STORE_LOCK:
        _get_owned_session(id, current_user.id)
        session = _SESSIONS[id]
        del _SESSIONS[id]
        if session.get("compat_mode"):
            response.status_code = status.HTTP_200_OK
            return {"deleted": True}
        response.status_code = status.HTTP_204_NO_CONTENT
        return None
