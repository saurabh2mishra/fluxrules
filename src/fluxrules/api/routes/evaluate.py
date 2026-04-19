from fastapi import APIRouter, Depends, HTTPException

from fluxrules.api.deps import get_rule_service
from fluxrules.api.schemas import EvaluateRequest, EvaluateResponse
from fluxrules.services.rule_service import RuleService

router = APIRouter(prefix="/v1/rulesets", tags=["rules"])


@router.post("/{ruleset_id}/evaluate", response_model=EvaluateResponse)
def evaluate_ruleset(
    ruleset_id: str,
    request: EvaluateRequest,
    service: RuleService = Depends(get_rule_service),
) -> EvaluateResponse:
    try:
        result = service.evaluate(ruleset_id, request.facts)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    return EvaluateResponse(
        execution_id=result.execution_id,
        matched_rules=result.matched_rule_ids,
        actions=result.actions,
    )
