"""Evaluation endpoint for the SDK (simple, no-auth version)."""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from fluxrules.api.schemas import ComparisonIssueResponse, comparison_issues
from fluxrules.domain.errors import UncomparableValuesError
from fluxrules.domain.models import Ruleset
from fluxrules.services.rule_service import RuleService

router = APIRouter(tags=["evaluate"])


class EvaluateRequest(BaseModel):
    """Request to evaluate a ruleset."""

    ruleset: Ruleset = Field(..., description="The ruleset to evaluate")
    facts: dict[str, object] = Field(..., description="Facts to evaluate against")


class EvaluateResponse(BaseModel):
    """Response from evaluation."""

    execution_id: str
    matched_rules: list[int]
    actions: list[str]
    comparison_issues: list[ComparisonIssueResponse] = Field(default_factory=list)


_service = RuleService.create()


@router.post("/evaluate", response_model=EvaluateResponse)
def evaluate_ruleset(request: EvaluateRequest) -> EvaluateResponse:
    """Evaluate a ruleset against facts (SDK endpoint)."""
    try:
        result = _service.evaluate_inline(request.ruleset, request.facts)
        _service.execution_store.save(result)
        return EvaluateResponse(
            execution_id=result.execution_id,
            matched_rules=result.fired_rules,
            actions=result.actions,
            comparison_issues=comparison_issues(result),
        )
    except UncomparableValuesError:
        raise  # answered with 422 by the app's exception handler
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
