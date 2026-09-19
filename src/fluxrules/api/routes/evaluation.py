"""Evaluation and explanation endpoints.

Provides:
- POST /evaluate - evaluate rules against facts
- POST /evaluate/bulk - evaluate rules against many fact sets in one request
- GET  /explain/{execution_id} - retrieve explanation of a prior evaluation
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


def _load_domain_rules(
    db: Session,
    ruleset_id: str | None,
    rule_ids: list[int] | None,
) -> list:
    """Load enabled rules matching the filters as domain rules, once.

    Returned in priority order so the same compiled set can be reused across
    many fact sets in a bulk evaluation.
    """
    from fluxrules.api.models.rule import Rule as OrmRule
    from fluxrules.persistence.mappers import orm_rule_to_canonical

    query = db.query(OrmRule).filter(OrmRule.enabled)
    if rule_ids:
        query = query.filter(OrmRule.id.in_(rule_ids))
    if ruleset_id:
        query = query.filter(OrmRule.group == ruleset_id)
    orm_rules = query.order_by(OrmRule.priority.desc()).all()
    # Load canonically: reading condition_dsl straight from the column keeps
    # OR/NOT/nested logic intact. The flat view would drop it and the rule
    # would then match nothing, quietly.
    return [(orm_rule.id, orm_rule_to_canonical(orm_rule)) for orm_rule in orm_rules]


def _match_facts(domain_rules: list, facts: dict[str, Any]) -> tuple[list, list[str]]:
    """Match a single fact set against pre-loaded canonical rules."""
    from fluxrules.domain.dsl.evaluator import UnsupportedDSLNodeError, evaluate_dsl

    matched_ids: list = []
    actions: list[str] = []
    for rule_id, rule in domain_rules:
        try:
            outcome = evaluate_dsl(rule.condition_dsl, facts)
        except UnsupportedDSLNodeError:
            # Declining loudly beats matching by accident; a stateful rule
            # needs a real engine, not this route.
            logger.warning(
                "Rule %s uses a DSL node this route cannot evaluate; skipped",
                rule_id,
            )
            continue
        if outcome:
            matched_ids.append(rule_id)
            for action in rule.actions:
                if action and action not in actions:
                    actions.append(action)
    return matched_ids, actions


@router.post("/evaluate", response_model=EvaluateResponse)
def evaluate(
    request: EvaluateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> EvaluateResponse:
    """Evaluate rules against provided facts.

    If ``ruleset_id`` is given, evaluates that SDK ruleset.
    Otherwise falls back to evaluating all enabled DB rules.
    """
    if request.ruleset_id:
        # Try SDK-level evaluation first
        from fluxrules.services.rule_service import RuleService as SdkRuleService

        try:
            svc = SdkRuleService.create()
            result = svc.evaluate_ruleset(request.ruleset_id, request.facts)
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

    # Database-level evaluation: match facts against enabled rules
    domain_rules = _load_domain_rules(db, request.ruleset_id, request.rule_ids)
    matched_ids, actions = _match_facts(domain_rules, request.facts)

    execution_id = str(uuid.uuid4())
    resp = EvaluateResponse(
        execution_id=execution_id,
        ruleset_group=request.ruleset_id or "all",
        matched_rules=matched_ids,
        actions=actions,
        facts=request.facts,
    )
    _execution_store[execution_id] = resp.model_dump()
    return resp


@router.post("/evaluate/bulk", response_model=BulkEvaluateResponse)
def evaluate_bulk(
    request: BulkEvaluateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> BulkEvaluateResponse:
    """Evaluate many fact sets against the same rules in one request.

    The matching rules are loaded once and reused for every fact set, which
    keeps throughput high when running large batches. Each result carries its
    own ``execution_id`` that can be passed to ``/explain``.
    """
    domain_rules = _load_domain_rules(db, request.ruleset_id, request.rule_ids)
    ruleset_group = request.ruleset_id or "all"

    results: list[BulkEvaluateResult] = []
    for index, facts in enumerate(request.facts):
        matched_ids, actions = _match_facts(domain_rules, facts)
        execution_id = str(uuid.uuid4())
        _execution_store[execution_id] = {
            "execution_id": execution_id,
            "ruleset_group": ruleset_group,
            "matched_rules": matched_ids,
            "actions": actions,
            "facts": facts,
        }
        results.append(
            BulkEvaluateResult(
                index=index,
                execution_id=execution_id,
                matched_rules=matched_ids,
                actions=actions,
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
    # Check in-memory store first
    if execution_id in _execution_store:
        return _execution_store[execution_id]

    # Check SDK RuleService store
    from fluxrules.services.rule_service import RuleService as SdkRuleService

    try:
        svc = SdkRuleService.create()
        result = svc.explain(execution_id)
        return {
            "execution_id": result.execution_id,
            "ruleset_group": result.ruleset_group,
            "matched_rules": result.matched_rule_ids,
            "actions": result.actions,
            "facts": {},
        }
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Execution '{execution_id}' not found")
