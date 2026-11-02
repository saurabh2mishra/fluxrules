"""Evaluation and explanation endpoints.

These endpoints stay intentionally thin: they adapt HTTP requests into a
canonical :class:`fluxrules.services.rule_service.RuleService` call instead of
re-implementing rule matching in the route layer.
"""

from __future__ import annotations

import logging
import threading
import uuid
from collections import OrderedDict
from collections.abc import Callable
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


class _ExecutionStore:
    """The most recent evaluation records, for ``GET /explain/{execution_id}``.

    Kept in memory and bounded: adding a record past the limit removes the
    oldest one. Reading a record does not change its age. Writes take a lock
    because FastAPI runs these sync routes in a thread pool.
    """

    def __init__(self, max_records: Callable[[], int]) -> None:
        self._records: OrderedDict[str, dict[str, Any]] = OrderedDict()
        self._max_records = max_records
        self._lock = threading.Lock()

    def __setitem__(self, execution_id: str, record: dict[str, Any]) -> None:
        limit = self._max_records()
        with self._lock:
            if limit <= 0:
                self._records.clear()
                return
            self._records[execution_id] = record
            self._records.move_to_end(execution_id)
            while len(self._records) > limit:
                self._records.popitem(last=False)

    def get(self, execution_id: str) -> dict[str, Any] | None:
        return self._records.get(execution_id)

    def __contains__(self, execution_id: object) -> bool:
        return execution_id in self._records

    def __len__(self) -> int:
        return len(self._records)

    def clear(self) -> None:
        with self._lock:
            self._records.clear()


def _explain_store_limit() -> int:
    from fluxrules.api.config import settings

    return settings.EXPLAIN_STORE_MAX_RECORDS


# In-memory store for execution results, read by /explain.
_execution_store = _ExecutionStore(_explain_store_limit)


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

    canonical_rules = tuple(
        orm_rule_to_canonical(orm_rule).to_engine_rule() for orm_rule in orm_rules
    )
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
        fired_rules=[],
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
                matched_rules=result.fired_rules,
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
        matched_rules=result.fired_rules,
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
    ruleset_group, results = evaluate_many(db, request.facts, request.ruleset_id, request.rule_ids)
    return BulkEvaluateResponse(
        count=len(results),
        ruleset_group=ruleset_group,
        results=results,
    )


def evaluate_many(
    db: Session,
    facts_list: list[dict[str, Any]],
    ruleset_id: str | None,
    rule_ids: list[int] | None,
) -> tuple[str, list[BulkEvaluateResult]]:
    """Evaluate each fact on its own against the same stored rules.

    Shared by ``/evaluate/bulk`` and ``/sessions/{id}/evaluate``. Each result is
    recorded for ``/explain``. Returns the ruleset group and one result per
    fact, in input order.
    """
    service = RuleService.create()
    ruleset = _load_ruleset(db, ruleset_id, rule_ids)
    ruleset_group = ruleset_id or "all"

    results: list[BulkEvaluateResult] = []
    for index, facts in enumerate(facts_list):
        if not ruleset.rules:
            result = _empty_match_result(ruleset_group)
        else:
            result = service.evaluate_inline(ruleset, facts)
        _execution_store[result.execution_id] = {
            "execution_id": result.execution_id,
            "ruleset_group": ruleset_group,
            "matched_rules": result.fired_rules,
            "actions": result.actions,
            "facts": facts,
        }
        results.append(
            BulkEvaluateResult(
                index=index,
                execution_id=result.execution_id,
                matched_rules=result.fired_rules,
                actions=result.actions,
            )
        )
    return ruleset_group, results


@router.get("/explain/{execution_id}")
def explain(
    execution_id: str,
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Retrieve the explanation for a prior evaluation."""
    record = _execution_store.get(execution_id)
    if record is not None:
        return record

    try:
        result = RuleService.create().explain(execution_id)
        return {
            "execution_id": result.execution_id,
            "ruleset_group": result.ruleset_group,
            "matched_rules": result.fired_rules,
            "actions": result.actions,
            "facts": {},
        }
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Execution '{execution_id}' not found")
