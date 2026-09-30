from __future__ import annotations

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jwt import InvalidTokenError
from sqlalchemy.orm import Session

from fluxrules.adapters.repository.in_memory import (
    InMemoryExecutionStore,
    InMemoryRulesetRepository,
)
from fluxrules.api.config import get_secret_key, settings
from fluxrules.api.database import get_db
from fluxrules.services.reference_evaluator import ReferenceEvaluator
from fluxrules.services.rule_service import RuleService

_service: RuleService | None = None

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/token", auto_error=True)


def get_rule_service() -> RuleService:
    global _service
    if _service is None:
        _service = RuleService(
            engine=ReferenceEvaluator(),
            repository=InMemoryRulesetRepository(),
            execution_store=InMemoryExecutionStore(),
        )
    return _service


def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
):
    """Decode JWT and return the authenticated user."""
    from fluxrules.api.models.user import User

    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, get_secret_key(), algorithms=[settings.ALGORITHM])
        username: str | None = payload.get("sub")
        if username is None:
            raise credentials_exception
    except InvalidTokenError:
        raise credentials_exception

    user = db.query(User).filter(User.username == username).first()
    if user is None:
        raise credentials_exception
    return user


def get_current_admin(
    current_user=Depends(get_current_user),
):
    """Require the current user to have admin role."""
    if current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required",
        )
    return current_user
