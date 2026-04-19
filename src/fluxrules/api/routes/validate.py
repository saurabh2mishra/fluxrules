from fastapi import APIRouter, Depends, HTTPException

from fluxrules.api.deps import get_rule_service
from fluxrules.api.schemas import ValidateResponse
from fluxrules.services.rule_service import RuleService

router = APIRouter(prefix="/v1/rulesets", tags=["rules"])


@router.get("/{ruleset_id}/validate", response_model=ValidateResponse)
def validate_ruleset(ruleset_id: str, service: RuleService = Depends(get_rule_service)) -> ValidateResponse:
    ruleset = service.repository.get(ruleset_id)
    if ruleset is None:
        raise HTTPException(status_code=404, detail=f"Unknown ruleset '{ruleset_id}'")
    return ValidateResponse(issues=service.validate(ruleset))
