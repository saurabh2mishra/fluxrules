"""Validation endpoint for the SDK."""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from fluxrules.domain.models import Ruleset
from fluxrules.services.validation_service import ValidationService

router = APIRouter(tags=["validate"])


class ValidateRequest(BaseModel):
    """Request to validate a ruleset."""

    ruleset: Ruleset = Field(..., description="The ruleset to validate")


class ValidateResponse(BaseModel):
    """Response from validation."""

    issues: list[str]


_validator = ValidationService()


@router.post("/validate", response_model=ValidateResponse)
def validate_ruleset(request: ValidateRequest) -> ValidateResponse:
    """Validate a ruleset and return any issues found."""
    try:
        issues = _validator.validate_ruleset(request.ruleset)
        return ValidateResponse(issues=issues)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
