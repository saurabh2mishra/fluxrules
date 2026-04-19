from fastapi import APIRouter, Depends, HTTPException

from fluxrules.api.deps import get_rule_service
from fluxrules.api.schemas import ExplainResponse
from fluxrules.services.rule_service import RuleService

router = APIRouter(prefix="/v1/executions", tags=["rules"])


@router.get("/{execution_id}", response_model=ExplainResponse)
def explain_execution(
    execution_id: str,
    service: RuleService = Depends(get_rule_service),
) -> ExplainResponse:
    try:
        result = service.explain(execution_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    return ExplainResponse(
        execution_id=result.execution_id,
        matched_rules=result.matched_rule_ids,
        actions=result.actions,
        trace=result.trace,
    )
