"""Ruleset management endpoints.

Provides REST API for listing and managing rulesets (groups of rules).
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from fluxrules.api.database import get_db
from fluxrules.api.deps import get_current_user
from fluxrules.api.models.rule import Rule
from fluxrules.api.models.user import User
from fluxrules.api.routes.rules import serialize_rule

router = APIRouter(prefix="/rulesets", tags=["rulesets"])


@router.get("")
def list_rulesets(
    skip: int = Query(0, ge=0, description="Number of rulesets to skip"),
    limit: int = Query(100, ge=1, le=1000, description="Maximum rulesets to return"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[dict[str, Any]]:
    """List all rulesets (distinct groups) with summary info."""
    groups = (
        db.query(
            Rule.group,
            func.count(Rule.id).label("rule_count"),
        )
        .group_by(Rule.group)
        .order_by(Rule.group)
        .offset(skip)
        .limit(limit)
        .all()
    )
    result = []
    for group_name, count in groups:
        result.append(
            {
                "group": group_name or "",
                "rule_count": count,
            }
        )
    return result


@router.get("/{group_id}")
def get_ruleset(
    group_id: str,
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Get a ruleset (all rules in a group) by group ID."""
    rules = (
        db.query(Rule)
        .filter(Rule.group == group_id)
        .order_by(Rule.priority.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )
    if not rules:
        raise HTTPException(status_code=404, detail=f"Ruleset '{group_id}' not found")
    return {
        "group": group_id,
        "rule_count": len(rules),
        "rules": [serialize_rule(r) for r in rules],
    }


@router.put("/{group_id}")
def update_ruleset(
    group_id: str,
    payload: dict[str, Any],
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Update properties of all rules in a ruleset (group).

    Supported fields in payload: ``enabled``, ``priority``, ``description``.
    """
    rules = db.query(Rule).filter(Rule.group == group_id).all()
    if not rules:
        raise HTTPException(status_code=404, detail=f"Ruleset '{group_id}' not found")

    allowed = {"enabled", "priority", "description"}
    updates = {k: v for k, v in payload.items() if k in allowed}

    for rule in rules:
        for key, value in updates.items():
            setattr(rule, key, value)

    db.commit()

    # Refresh
    rules = db.query(Rule).filter(Rule.group == group_id).order_by(Rule.priority.desc()).all()
    return {
        "group": group_id,
        "updated_count": len(rules),
        "rules": [serialize_rule(r) for r in rules],
    }
