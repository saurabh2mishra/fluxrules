"""SDK-level routes for the embeddable rule engine.

These routes expose the :class:`~fluxrules.services.rule_service.RuleService`
over HTTP and are intentionally separate from the ORM-backed CRUD routes in
``fluxrules.api.routes.rules``.

Endpoints
---------
POST /v1/rulesets/{ruleset_id}/evaluate
    Evaluate a persisted ruleset against a facts payload.

POST /v1/rulesets/{ruleset_id}/simulate
    Run a ruleset against a list of fact samples and return per-sample results.

GET  /v1/executions/{execution_id}
    Retrieve the explanation for a prior evaluation.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from fluxrules.api.deps import get_rule_service

router = APIRouter(prefix="/v1", tags=["SDK"])


#  Request / Response schemas


class EvaluateRequest(BaseModel):
    facts: dict[str, Any]


class EvaluateResponse(BaseModel):
    execution_id: str
    ruleset_group: str
    matched_rules: list[int]
    actions: list[str]


class SimulateRequest(BaseModel):
    samples: list[dict[str, Any]]


class SimulateResponse(BaseModel):
    results: list[EvaluateResponse]


#  Endpoints


@router.post("/rulesets/{ruleset_id}/evaluate", response_model=EvaluateResponse)
def evaluate_ruleset(
    ruleset_id: str,
    body: EvaluateRequest,
    service=Depends(get_rule_service),
) -> EvaluateResponse:
    try:
        result = service.evaluate_ruleset(ruleset_id, body.facts)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return EvaluateResponse(
        execution_id=result.execution_id,
        ruleset_group=result.ruleset_group,
        matched_rules=result.matched_rule_ids,
        actions=result.actions,
    )


@router.post("/rulesets/{ruleset_id}/simulate")
def simulate_ruleset(
    ruleset_id: str,
    body: SimulateRequest,
    service=Depends(get_rule_service),
) -> list[EvaluateResponse]:
    try:
        results = service.simulate(ruleset_id, body.samples)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return [
        EvaluateResponse(
            execution_id=result.execution_id,
            ruleset_group=result.ruleset_group,
            matched_rules=result.matched_rule_ids,
            actions=result.actions,
        )
        for result in results
    ]


@router.get("/executions/{execution_id}", response_model=EvaluateResponse)
def get_execution(
    execution_id: str,
    service=Depends(get_rule_service),
) -> EvaluateResponse:
    try:
        result = service.explain(execution_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return EvaluateResponse(
        execution_id=result.execution_id,
        ruleset_group=result.ruleset_group,
        matched_rules=result.matched_rule_ids,
        actions=result.actions,
    )
