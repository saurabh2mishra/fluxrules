"""Evaluation and explanation endpoints.

These endpoints stay intentionally thin: they adapt HTTP requests into a
canonical :class:`fluxrules.services.rule_service.RuleService` call instead of
re-implementing rule matching in the route layer.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from fluxrules.api.database import get_db
from fluxrules.api.deps import get_current_user
from fluxrules.api.models.user import User
from fluxrules.domain.models import EvaluationResult, Ruleset
from fluxrules.persistence.mappers import orm_rule_to_canonical
from fluxrules.services.rule_service import RuleService

logger = logging.getLogger(__name__)

router = APIRouter(tags=["evaluation"])


class EvaluateRequest(BaseModel):
    """Request body for /evaluate endpoint."""

    facts: dict[str, Any] = Field(..., description="Facts to evaluate against rules")
    ruleset_id: str | None = Field(None, description="Optional ruleset/group ID to evaluate")
    rule_ids: list[int] | None = Field(None, description="Optional specific rule IDs")


class EvaluateResponse(BaseModel):
    execution_id: str
    ruleset_group: Any
    matched_rules: list[Any]
    actions: list[str]
    facts: dict[str, Any]


class BulkEvaluateRequest(BaseModel):
    """Request body for /evaluate/bulk endpoint."""

    facts: list[dict[str, Any]] = Field(
        ..., description="Fact sets to evaluate, one evaluation per entry"
    )
    ruleset_id: str | None = Field(None, description="Optional ruleset/group ID to evaluate")
    rule_ids: list[int] | None = Field(None, description="Optional specific rule IDs")


class BulkEvaluateResult(BaseModel):
    index: int
    execution_id: str
    matched_rules: list[Any]
    actions: list[str]


class BulkEvaluateResponse(BaseModel):
    count: int
    ruleset_group: Any
    results: list[BulkEvaluateResult]


# In-memory store for execution results (shared with SDK RuleService)
_execution_store: dict[str, dict[str, Any]] = {}


def _load_ruleset(
    db: Session,
    ruleset_id: str | None,
    rule_ids: list[int] | None,
) -> Ruleset:
    """Load the matching persisted rules as a canonical ruleset."""
    from fluxrules.api.models.rule import Rule as OrmRule

    query = db.query(OrmRule).filter(OrmRule.enabled)
    if rule_ids:
        query = query.filter(OrmRule.id.in_(rule_ids))
    if ruleset_id:
        query = query.filter(OrmRule.group == ruleset_id)
    orm_rules = query.order_by(OrmRule.priority.desc()).all()

    canonical_rules = tuple(orm_rule_to_canonical(orm_rule).to_engine_rule() for orm_rule in orm_rules)
    return Ruleset(group=ruleset_id or "all", rules=canonical_rules)


def _empty_response(ruleset_group: str, facts: dict[str, Any]) -> EvaluateResponse:
    """Return an empty-but-valid evaluation response."""
    return EvaluateResponse(
        execution_id=str(uuid.uuid4()),
        ruleset_group=ruleset_group,
        matched_rules=[],
        actions=[],
        facts=facts,
    )


def _empty_match_result(ruleset_group: str) -> EvaluationResult:
    """Return an empty match payload for bulk evaluation."""
    return EvaluationResult(
        ruleset_group=ruleset_group,
        matched_rule_ids=[],
        actions=[],
    )


@router.post("/evaluate", response_model=EvaluateResponse)
def evaluate(
    request: EvaluateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> EvaluateResponse:
    """Evaluate rules against provided facts.

    If ``ruleset_id`` is given, evaluates that SDK ruleset when it is already in
    the in-memory repository. Otherwise it loads the matching persisted rules and
    evaluates them through the canonical RuleService engine path.
    """
    if request.ruleset_id:
        try:
            service = RuleService.create()
            result = service.evaluate_ruleset(request.ruleset_id, request.facts)
            resp = EvaluateResponse(
                execution_id=result.execution_id,
                ruleset_group=result.ruleset_group,
                matched_rules=result.matched_rule_ids,
                actions=result.actions,
                facts=request.facts,
            )
            _execution_store[result.execution_id] = resp.model_dump()
            return resp
        except KeyError:
            pass

    service = RuleService.create()
    ruleset = _load_ruleset(db, request.ruleset_id, request.rule_ids)
    if not ruleset.rules:
        resp = _empty_response(request.ruleset_id or "all", request.facts)
        _execution_store[resp.execution_id] = resp.model_dump()
        return resp

    result = service.evaluate_inline(ruleset, request.facts)

    resp = EvaluateResponse(
        execution_id=result.execution_id,
        ruleset_group=result.ruleset_group,
        matched_rules=result.matched_rule_ids,
        actions=result.actions,
        facts=request.facts,
    )
    _execution_store[result.execution_id] = resp.model_dump()
    return resp


@router.post("/evaluate/bulk", response_model=BulkEvaluateResponse)
def evaluate_bulk(
    request: BulkEvaluateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> BulkEvaluateResponse:
    """Evaluate many fact sets against the same rules in one request."""
    service = RuleService.create()
    ruleset = _load_ruleset(db, request.ruleset_id, request.rule_ids)
    ruleset_group = request.ruleset_id or "all"

    results: list[BulkEvaluateResult] = []
    for index, facts in enumerate(request.facts):
        if not ruleset.rules:
            result = _empty_match_result(ruleset_group)
        else:
            result = service.evaluate_inline(ruleset, facts)
        _execution_store[result.execution_id] = {
            "execution_id": result.execution_id,
            "ruleset_group": ruleset_group,
            "matched_rules": result.matched_rule_ids,
            "actions": result.actions,
            "facts": facts,
        }
        results.append(
            BulkEvaluateResult(
                index=index,
                execution_id=result.execution_id,
                matched_rules=result.matched_rule_ids,
                actions=result.actions,
            )
        )

    return BulkEvaluateResponse(
        count=len(results),
        ruleset_group=ruleset_group,
        results=results,
    )


@router.get("/explain/{execution_id}")
def explain(
    execution_id: str,
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Retrieve the explanation for a prior evaluation."""
    if execution_id in _execution_store:
        return _execution_store[execution_id]

    try:
        result = RuleService.create().explain(execution_id)
        return {
            "execution_id": result.execution_id,
            "ruleset_group": result.ruleset_group,
            "matched_rules": result.matched_rule_ids,
            "actions": result.actions,
            "facts": {},
        }
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Execution '{execution_id}' not found")
