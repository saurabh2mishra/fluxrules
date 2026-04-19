from fastapi import APIRouter, Depends, HTTPException

from fluxrules.api.deps import get_rule_service
from fluxrules.api.schemas import EvaluateResponse, SimulateRequest
from fluxrules.services.rule_service import RuleService

router = APIRouter(prefix="/v1/rulesets", tags=["rules"])


@router.post("/{ruleset_id}/simulate", response_model=list[EvaluateResponse])
def simulate_ruleset(
    ruleset_id: str,
    request: SimulateRequest,
    service: RuleService = Depends(get_rule_service),
) -> list[EvaluateResponse]:
    try:
        results = service.simulate(ruleset_id, request.samples)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    return [
        EvaluateResponse(
            execution_id=result.execution_id,
            matched_rules=result.matched_rule_ids,
            actions=result.actions,
        )
        for result in results
    ]
